import datetime
import hashlib
import logging
import os
from typing import Annotated, List, Optional
from uuid import UUID
import uuid
import aiofiles
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, Response, UploadFile, status
from fastapi.responses import JSONResponse
from sqlalchemy import asc, case, desc, distinct, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from fastapi_jwt_auth import AuthJWT
from pydantic import BaseModel, EmailStr, Field, StringConstraints, field_validator
from src.middlewares.auth import authenticate
from src.models.addon import AddOn, AddOnType
from src.database import get_session
from src.models.versions import Version
# from slowapi import Limiter
from slowapi.util import get_ipaddr

logger = logging.getLogger(__name__)

router = APIRouter()

class VersionResponse(BaseModel):
    uuid: UUID
    addon_uuid: UUID
    version: str
    description: str
    download_url: str
    file_hash: str
    created_at: datetime.datetime

    class Config:
        from_attributes = True

class VersionListResponse(BaseModel):
    items: List[VersionResponse]
    total_count: int
    page: int
    per_page: int

class VersionCreate(BaseModel):
    version: Annotated[str, StringConstraints(min_length=1, max_length=64)] = Field(description="Version string (e.g., '1.0.0', '2.1-beta')")
    description: Annotated[str, StringConstraints(min_length=10)] = Field(description="Description of the changes in this version")
    download_url: Annotated[str, StringConstraints(min_length=10, max_length=256)] = Field(description="URL to download the version file")
    file_hash: Annotated[str, StringConstraints(min_length=32, max_length=128)] = Field(description="Version file hash (e.g. SHA256)")

class VersionUpdate(BaseModel):
    description: Optional[Annotated[str, StringConstraints(min_length=10)]] = Field(None, description="New description of changes")
    download_url: Optional[Annotated[str, StringConstraints(min_length=10, max_length=256)]] = Field(None, description="New download URL")
    file_hash: Optional[Annotated[str, StringConstraints(min_length=32, max_length=128)]] = Field(None, description="New file hash")


@router.get("/addons/{addon_uuid}/versions", response_model=VersionListResponse, status_code=status.HTTP_200_OK)
async def get_addon_versions(
    addon_uuid: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(10, ge=1, le=100, description="Number of items per page"),
    sort_order: Optional[str] = Query(
        "desc",
        description="Sort order.",
        regex="^(asc|desc)$"
    )
):
    addon_exists = await session.execute(select(AddOn.uuid).where(AddOn.uuid == addon_uuid))
    if not addon_exists.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Addon not found.")

    query_statement = select(Version).where(Version.addon_uuid == addon_uuid)

    total_count_result = await session.execute(
        select(func.count(Version.uuid)).where(Version.addon_uuid == addon_uuid)
    )
    total_count = total_count_result.scalar_one()

    if sort_order == "desc":
        query_statement = query_statement.order_by(desc(Version.created_at))
    else:
        query_statement = query_statement.order_by(asc(Version.created_at))

    offset = (page - 1) * per_page
    query_statement = query_statement.offset(offset).limit(per_page)

    result = await session.execute(query_statement)
    versions = result.scalars().all()

    return VersionListResponse(
        items=[VersionResponse.model_validate(v) for v in versions],
        total_count=total_count,
        page=page,
        per_page=per_page
    )

@router.get("/addons/{addon_uuid}/versions/{version_uuid}", response_model=VersionResponse, status_code=status.HTTP_200_OK)
async def get_version_details(
    addon_uuid: uuid.UUID,
    version_uuid: uuid.UUID,
    session: AsyncSession = Depends(get_session)
):
    addon_exists = await session.execute(select(AddOn.uuid).where(AddOn.uuid == addon_uuid))
    if not addon_exists.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Addon not found.")
    
    query = select(Version).where(Version.addon_uuid == addon_uuid, Version.uuid == version_uuid)
    result = await session.execute(query)
    version_obj = result.scalar_one_or_none()

    if not version_obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Addon version not found")
    
    return VersionResponse.model_validate(version_obj)

@router.get("/addons/{addon_uuid}/versions/latest", response_model=VersionResponse, status_code=status.HTTP_200_OK)
async def get_latest_addon_version(
    addon_uuid: uuid.UUID,
    session: AsyncSession = Depends(get_session)
):
    addon_exists = await session.execute(select(AddOn.uuid).where(AddOn.uuid == addon_uuid))
    if not addon_exists.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Addon not found.")

    query = select(Version).where(Version.addon_uuid == addon_uuid).order_by(desc(Version.created_at)).limit(1)
    result = await session.execute(query)
    latest_version = result.scalar_one_or_none()

    if not latest_version:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="There are no versions available for this addon.")

    return VersionResponse.model_validate(latest_version)

MAX_FILE_SIZE_BYTES = 15 * 1024 * 1024
FILES_DIR = "files"

@router.post("/addons/{addon_uuid}/versions", response_model=VersionResponse, status_code=status.HTTP_201_CREATED, dependencies=[Depends(authenticate)])
async def add_new_addon_version(
    addon_uuid: uuid.UUID,
    version: Annotated[str, StringConstraints(min_length=1, max_length=64)] = Form(..., description="Version string (e.g., '1.0.0', '2.1-beta')"),
    description: Annotated[str, StringConstraints(min_length=10)] = Form(..., description="Description of the changes in this version"),
    file: UploadFile = File(..., description="Addon version file (max. 15 MB)"),
    session: AsyncSession = Depends(get_session),
    Authorize: AuthJWT = Depends()
):
    current_user_uuid = UUID(Authorize.get_jwt_subject())
    
    file_path_on_disk = None

    db_addon = await session.execute(select(AddOn).where(AddOn.uuid == addon_uuid))
    addon_obj = db_addon.scalar_one_or_none()
    if not addon_obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Addon not found.")
    if addon_obj.user_uuid != current_user_uuid:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient rights: You are not the author of this addon.")

    existing_version_by_num = await session.execute(
        select(Version).where(
            Version.addon_uuid == addon_uuid,
            func.lower(Version.version) == func.lower(version)
        )
    )
    if existing_version_by_num.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Version '{version}' already exists for this addon.")
    
    file_content = await file.read()

    if file.size is not None and file.size > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File size exceeds {MAX_FILE_SIZE_BYTES / (1024 * 1024):.0f} MB (Current: {file.size / (1024*1024):.2f} MB)."
        )
    if not file_content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="The uploaded file is empty.")

    file_hash = hashlib.sha256(file_content).hexdigest()
    
    file_extension = ""
    if file.filename:
        name, ext = os.path.splitext(file.filename)
        if ext:
            file_extension = ext
    
    file_name_on_disk = f"{file_hash}{file_extension}"
    file_path_on_disk = os.path.join(FILES_DIR, file_name_on_disk)

    download_url = f"/files/{file_name_on_disk}" 

    existing_version_by_hash = await session.execute(
        select(Version.uuid).where(Version.file_hash == file_hash)
    )
    if existing_version_by_hash.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="A file with this hash has already been downloaded.")
    
    existing_version_by_url = await session.execute(
        select(Version.uuid).where(Version.download_url == download_url)
    )
    if existing_version_by_url.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="The URL for the download is already in use.")

    try:
        os.makedirs(FILES_DIR, exist_ok=True)
        async with aiofiles.open(file_path_on_disk, "wb") as f:
            await f.write(file_content)
    except IOError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to save the file: {e}")
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Unexpected error when saving a file: {e}")

    new_version = Version(
        addon_uuid=addon_uuid,
        version=version,
        description=description,
        download_url=download_url,
        file_hash=file_hash
    )

    try:
        session.add(new_version)
        await session.commit()
        await session.refresh(new_version)
    except ValueError as e:
        await session.rollback()
        if file_path_on_disk and os.path.exists(file_path_on_disk):
            try:
                os.remove(file_path_on_disk)
            except OSError as exc:
                print(f"Warning: Could not delete file {file_path_on_disk} after DB rollback: {exc}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception:
        await session.rollback()
        if file_path_on_disk and os.path.exists(file_path_on_disk):
            try:
                os.remove(file_path_on_disk)
            except OSError as exc:
                print(f"Warning: Could not delete file {file_path_on_disk} after DB rollback: {exc}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to add a new version.")

    return VersionResponse.model_validate(new_version)

# @router.put("/addons/{addon_uuid}/versions/{version_uuid}", response_model=VersionResponse, status_code=status.HTTP_200_OK)
# async def update_addon_version(
#     addon_uuid: uuid.UUID,
#     version_uuid: uuid.UUID,
#     version: Annotated[Optional[str], StringConstraints(min_length=1, max_length=64)] = Form(None, description="Новая строка версии (например, '1.0.0', '2.1-beta')"),
#     description: Annotated[Optional[str], StringConstraints(min_length=10)] = Form(None, description="Новое описание изменений в этой версии"),
#     file: UploadFile = File(None, description="Новый файл версии дополнения (макс. 15 МБ)"),
#     session: AsyncSession = Depends(get_session),
#     Authorize: AuthJWT = Depends()
# ):

#     current_user_uuid = UUID(Authorize.get_jwt_subject())
    
#     new_file_path_on_disk = None
#     old_file_path_on_disk = None

#     db_addon = await session.execute(select(AddOn).where(AddOn.uuid == addon_uuid))
#     addon_obj = db_addon.scalar_one_or_none()
#     if not addon_obj:
#         raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Addon not found.")
#     if addon_obj.user_uuid != current_user_uuid:
#         raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient rights: You are not the author of this addon.")


#     query = select(Version).where(Version.addon_uuid == addon_uuid, Version.uuid == version_uuid)
#     result = await session.execute(query)
#     version_to_update = result.scalar_one_or_none()

#     if not version_to_update:
#         raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No version of the addon was found.")
    
#     old_file_hash = version_to_update.file_hash
#     old_download_url = version_to_update.download_url
#     if old_download_url:
#         old_file_extension = os.path.splitext(old_download_url.split('/')[-1])[1]
#         old_file_path_on_disk = os.path.join(FILES_DIR, f"{old_file_hash}{old_file_extension}")

#     if file:
#         file_content = await file.read()

#         if file.size is not None and file.size > MAX_FILE_SIZE_BYTES:
#             raise HTTPException(
#                 status_code=status.HTTP_400_BAD_REQUEST,
#                 detail=f"File size exceeds {MAX_FILE_SIZE_BYTES / (1024 * 1024):.0f} MB (Current: {file.size / (1024*1024):.2f} MB)."
#             )
#         if not file_content:
#             raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="The uploaded file is empty.")

#         new_file_hash = hashlib.sha256(file_content).hexdigest()
        
#         file_extension = ""
#         if file.filename:
#             name, ext = os.path.splitext(file.filename)
#             if ext:
#                 file_extension = ext
        
#         new_file_name_on_disk = f"{new_file_hash}{file_extension}"
#         new_file_path_on_disk = os.path.join(FILES_DIR, new_file_name_on_disk)

#         new_download_url = f"/files/{new_file_name_on_disk}"

#         if new_file_hash != version_to_update.file_hash:
#             existing_hash_version = await session.execute(
#                 select(Version.uuid).where(
#                     Version.file_hash == new_file_hash,
#                     Version.uuid != version_uuid 
#                 )
#             )
#             if existing_hash_version.scalar_one_or_none():
#                 raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="A file with this hash already exists for another version.")
        
#         if new_download_url != version_to_update.download_url:
#             existing_url_version = await session.execute(
#                 select(Version.uuid).where(
#                     Version.download_url == new_download_url,
#                     Version.uuid != version_uuid
#                 )
#             )
#             if existing_url_version.scalar_one_or_none():
#                 raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="The download URL is already being used by another version.")

#         try:
#             os.makedirs(FILES_DIR, exist_ok=True)
#             async with aiofiles.open(new_file_path_on_disk, "wb") as f:
#                 await f.write(file_content)
            
#             version_to_update.file_hash = new_file_hash
#             version_to_update.download_url = new_download_url
#         except IOError as e:
#             raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to save a new file: {e}")
#         except Exception as e:
#             raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Unexpected error when saving a new file: {e}")

#     if version is not None:
#         version_to_update.version = version
#     if description is not None:
#         version_to_update.description = description
    
#     try:
#         await session.commit()
#         await session.refresh(version_to_update)

#         if file and old_file_path_on_disk and os.path.exists(old_file_path_on_disk):
#             try:
#                 os.remove(old_file_path_on_disk)
#             except OSError as exc:
#                 print(f"Warning: Could not delete old file {old_file_path_on_disk} after successful DB update: {exc}")

#     except Exception:
#         await session.rollback()
#         if new_file_path_on_disk and os.path.exists(new_file_path_on_disk):
#             try:
#                 os.remove(new_file_path_on_disk)
#             except OSError as exc:
#                 print(f"Warning: Could not delete new file {new_file_path_on_disk} after DB rollback: {exc}")
#         raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update the version information.")

#     return VersionResponse.model_validate(version_to_update)

@router.delete("/addons/{addon_uuid}/versions/{version_uuid}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(authenticate)])
async def delete_addon_version(
    addon_uuid: uuid.UUID,
    version_uuid: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    Authorize: AuthJWT = Depends()
):
    current_user_uuid = UUID(Authorize.get_jwt_subject())
    db_addon = await session.execute(select(AddOn).where(AddOn.uuid == addon_uuid))
    addon_obj = db_addon.scalar_one_or_none()
    if not addon_obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Addon not found.")
    if addon_obj.user_uuid != current_user_uuid:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient rights: You are not the author of this addon.")

    query = select(Version).where(Version.addon_uuid == addon_uuid, Version.uuid == version_uuid)
    result = await session.execute(query)
    version_to_delete = result.scalar_one_or_none()

    if not version_to_delete:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No version of the addon was found.")

    try:
        session.delete(version_to_delete)
        await session.commit()
    except Exception:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to remove version.")

    return Response(status_code=status.HTTP_204_NO_CONTENT)