import datetime
import logging
from typing import Annotated, Optional
from uuid import UUID
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy import asc, case, desc, distinct, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from fastapi_jwt_auth import AuthJWT
from pydantic import BaseModel, EmailStr, Field, StringConstraints, field_validator
from src.middlewares.auth import authenticate
from src.models.addon import AddOn, AddOnType
from sqlalchemy.orm import selectinload
from src.database import get_session
from src.models.user_likes import UserLike

# from slowapi import Limiter
from slowapi.util import get_ipaddr

logger = logging.getLogger(__name__)

router = APIRouter()

# limiter = Limiter(key_func=get_ipaddr, storage_uri="memory://")

class AddOnResponse(BaseModel):
    uuid: UUID
    user_uuid: UUID
    username: str
    name: str
    type: AddOnType
    short_description: str
    description: str
    downloads: int
    publish_date: datetime.datetime
    update_date: datetime.datetime
    likes_count: int = Field(..., description="Count of likes")

    class Config:
        from_attributes = True


class AddOnListResponse(BaseModel):
    items: list[AddOnResponse]
    total_count: int = Field(..., description="Total count of items")
    page: int = Field(..., description="Current page number")
    per_page: int = Field(..., description="Maximum number of items per page")

class AddOnCreate(BaseModel):
    name: str = Field(..., min_length=3, max_length=128, description="Name of the addon")
    type: AddOnType = Field(..., description="Type of the addon")
    short_description: str = Field(..., min_length=10, max_length=256, description="Short description of the addon")
    description: str = Field(..., min_length=20, description="Description of the addon")

class AddOnUpdate(BaseModel):
    name: Optional[Annotated[str, StringConstraints(min_length=3, max_length=128)]] = Field(None, description="Новое название дополнения")
    type: Optional[AddOnType] = Field(None, description="Новый тип дополнения")
    short_description: Optional[Annotated[str, StringConstraints(min_length=10, max_length=256)]] = Field(None, description="Новое краткое описание дополнения")
    description: Optional[Annotated[str, StringConstraints(min_length=20)]] = Field(None, description="Новое полное описание дополнения")


@router.get("/addons", response_model=AddOnListResponse, status_code=status.HTTP_200_OK)
async def get_addons(
    request: Request,
    session: AsyncSession = Depends(get_session),
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(10, ge=1, le=100, description="Number of items per page"),
    type: Optional[AddOnType] = Query(None, description="Filter by type"),
    user_uuid: Optional[UUID] = Query(None, description="Filter by user UUID"),
    search: Optional[str] = Query(None, description="Search query"),
    sort_by: Optional[str] = Query(
        "downloads",
        description="Sort by field",
        regex="^(name|publish_date|update_date|downloads|likes_count|relevance)$"
    ),
    sort_order: Optional[str] = Query(
        "desc",
        description="Sort order.",
        regex="^(asc|desc)$"
    ),
):
    query = select(
        AddOn,
        func.count(UserLike.uuid).label("likes_count"),
    ).outerjoin(UserLike, AddOn.uuid == UserLike.addon_uuid) \
    .group_by(AddOn.uuid) \
    .options(selectinload(AddOn.user))

    relevance_score_expr = None

    if search:
        search_terms = [term.strip() for term in search.lower().split() if term.strip()]

        relevance_score_expr = 0

        name_weight = 3
        short_description_weight = 2
        description_weight = 1

        filters_for_search = []

        for term in search_terms:
            relevance_score_expr += case(
                (AddOn.name.ilike(f"%{term}%"), name_weight),
                else_=0
            )
            relevance_score_expr += case(
                (AddOn.short_description.ilike(f"%{term}%"), short_description_weight),
                else_=0
            )
            relevance_score_expr += case(
                (AddOn.description.ilike(f"%{term}%"), description_weight),
                else_=0
            )

            filters_for_search.append(
                or_(
                    AddOn.name.ilike(f"%{term}%"),
                    AddOn.short_description.ilike(f"%{term}%"),
                    AddOn.description.ilike(f"%{term}%")
                )
            )
        
        if filters_for_search:
            query = query.where(or_(*filters_for_search))
            query = query.add_columns(relevance_score_expr.label("relevance_score"))
    
    elif sort_by == "relevance":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Sorting by relevance is only allowed with a search query."
        )

    if type:
        query = query.where(AddOn.type == type)
    if user_uuid:
        query = query.where(AddOn.user_uuid == user_uuid)
    
    sortable_fields = {
        "publish_date": AddOn.publish_date,
        "downloads": AddOn.downloads,
        "update_date": AddOn.update_date,
        "likes_count": func.count(UserLike.uuid)
    }

    if relevance_score_expr is not None:
        sortable_fields["relevance"] = relevance_score_expr 

    if sort_by not in sortable_fields:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"The field '{sort_by}' is not sortable. Available fields: {', '.join(sortable_fields.keys())}"
        )
    
    if sort_by == "relevance":
        query = query.order_by(desc(sortable_fields["relevance"]))
    else:
        sort_column = sortable_fields[sort_by]
        if sort_order == "desc":
            query = query.order_by(desc(sort_column))
        elif sort_order == "asc":
            query = query.order_by(asc(sort_column))
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"The sort order '{sort_order}' is invalid. Use 'desc' or 'asc'."
            )
        
    count_query = select(func.count(distinct(AddOn.uuid)))

    if type:
        count_query = count_query.where(AddOn.type == type)
    if user_uuid:
        count_query = count_query.where(AddOn.user_uuid == user_uuid)
    if search and filters_for_search:

        count_query = count_query.where(or_(*filters_for_search))
    
    total_count_result = await session.execute(count_query)
    total_count = total_count_result.scalar_one()

    offset = (page - 1) * per_page
    query = query.offset(offset).limit(per_page)

    result = await session.execute(query)

    results = result.all()

    addons_list_response = []
    for row in results:

        db_addon: AddOn = row[0]
        likes_count = row[1]

        addon_data = {
            "uuid": db_addon.uuid,
            "user_uuid": db_addon.user_uuid,
            "username": db_addon.user.username,
            "name": db_addon.name,
            "type": db_addon.type,
            "name": db_addon.name,
            "short_description": db_addon.short_description,
            "description": db_addon.description,
            "downloads": db_addon.downloads,
            "publish_date": db_addon.publish_date,
            "update_date": db_addon.update_date,
            "likes_count": likes_count
        }
        addons_list_response.append(AddOnResponse.model_validate(addon_data))

    return AddOnListResponse(
        items=addons_list_response,
        total_count=total_count,
        page=page,
        per_page=per_page
    )

@router.get("/addons/{addon_uuid}", response_model=AddOnResponse, status_code=status.HTTP_200_OK)
async def get_addon(
    addon_uuid: UUID,
    session: AsyncSession = Depends(get_session)
):
    # query = select(
    #     AddOn,
    #     func.count(UserLike.uuid).label("likes_count"),
    # ).outerjoin(UserLike, AddOn.uuid == UserLike.addon_uuid).where(
    #     AddOn.uuid == addon_uuid
    # ).group_by(AddOn.uuid)

    query = select(
        AddOn,
        func.count(UserLike.uuid).label("likes_count"),
    ).outerjoin(UserLike, AddOn.uuid == UserLike.addon_uuid) \
    .where(AddOn.uuid == addon_uuid) \
    .group_by(AddOn.uuid) \
    .options(selectinload(AddOn.user))


    result = await session.execute(query)

    addon_data_row = result.first()

    if not addon_data_row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Add-on now found."
        )

    db_addon: AddOn = addon_data_row[0]
    likes_count = addon_data_row[1]

    return AddOnResponse.model_validate({
        "uuid": db_addon.uuid,
        "user_uuid": db_addon.user_uuid,
        "username": db_addon.user.username,
        "name": db_addon.name,
        "type": db_addon.type,
        "short_description": db_addon.short_description,
        "description": db_addon.description,
        "downloads": db_addon.downloads,
        "publish_date": db_addon.publish_date,
        "update_date": db_addon.update_date,
        "likes_count": likes_count
    })



@router.post("/addons", response_model=AddOnResponse, status_code=status.HTTP_201_CREATED, dependencies=[Depends(authenticate)])
async def create_addon(
    addon_data: AddOnCreate,
    session: AsyncSession = Depends(get_session),
    Authorize: AuthJWT = Depends()
):
    current_user_uuid = UUID(Authorize.get_jwt_subject())
    existing_addon = await session.execute(
        select(AddOn).where(func.lower(AddOn.name) == func.lower(addon_data.name))
    )
    if existing_addon.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An addon with the same name already exists."
        )
    
    new_addon = AddOn(
        **addon_data.model_dump(),
        user_uuid=current_user_uuid,
    )

    session.add(new_addon)
    await session.commit()
    await session.refresh(new_addon)

    return AddOnResponse.model_validate({
        "uuid": new_addon.uuid,
        "user_uuid": new_addon.user_uuid,
        "name": new_addon.name,
        "type": new_addon.type,
        "short_description": new_addon.short_description,
        "description": new_addon.description,
        "downloads": new_addon.downloads,
        "publish_date": new_addon.publish_date,
        "update_date": new_addon.update_date,
        "likes_count": 0
    })

@router.put("/addons/{addon_uuid}", response_model=AddOnResponse, status_code=status.HTTP_200_OK, dependencies=[Depends(authenticate)])
async def update_addon(
    addon_uuid: UUID,
    addon_update_data: AddOnUpdate,
    session: AsyncSession = Depends(get_session),
    Authorize: AuthJWT = Depends()
):
    current_user_uuid = UUID(Authorize.get_jwt_subject())
    query = select(
        AddOn,
        func.count(UserLike.uuid).label("likes_count"),
    ).outerjoin(UserLike, AddOn.uuid == UserLike.addon_uuid).where(
        AddOn.uuid == addon_uuid
    ).group_by(AddOn.uuid)

    result = await session.execute(query)
    addon_data_row = result.first()

    if not addon_data_row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Add-on not found."
        )
    
    db_addon: AddOn = addon_data_row[0]
    original_likes_count  = addon_data_row[1]

    if db_addon.user_uuid != current_user_uuid:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not authorized to update this addon."
        )
    
    update_data = addon_update_data.model_dump(exclude_unset=True)

    if "name" in update_data and update_data["name"].lower() != db_addon.name.lower():
        existing_addon_with_new_name = await session.execute(
            select(AddOn.uuid).where(
                func.lower(AddOn.name) == func.lower(update_data["name"]),
                AddOn.uuid != addon_uuid
            )
        )
        if existing_addon_with_new_name.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="An addon with the same name already exists."
            )
    
    for key, value in update_data.items():
        setattr(db_addon, key, value)

    await session.commit()

    updated_addon_query = select(
        AddOn,
        func.count(UserLike.uuid).label("likes_count")
    ).outerjoin(UserLike, AddOn.uuid == UserLike.addon_uuid).where(
        AddOn.uuid == addon_uuid
    ).group_by(AddOn.uuid)

    updated_result = await session.execute(updated_addon_query)
    updated_addon_data_row = updated_result.first()

    if not updated_addon_data_row:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while updating the addon."
        )

    final_addon: AddOn = updated_addon_data_row[0]
    final_likes_count  = updated_addon_data_row[1]

    return AddOnResponse.model_validate({
        "uuid": final_addon.uuid,
        "user_uuid": final_addon.user_uuid,
        "name": final_addon.name,
        "type": final_addon.type,
        "short_description": final_addon.short_description,
        "description": final_addon.description,
        "downloads": final_addon.downloads,
        "publish_date": final_addon.publish_date,
        "update_date": final_addon.update_date,
        "likes_count": final_likes_count
    })

@router.delete("/addons/{addon_uuid}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(authenticate)])
async def delete_addon(
    addon_uuid: UUID,
    session: AsyncSession = Depends(get_session),
    Authorize: AuthJWT = Depends()
):
    current_user_uuid = UUID(Authorize.get_jwt_subject())

    db_addon = await session.execute(select(AddOn).where(AddOn.uuid == addon_uuid))
    addon_to_delete = db_addon.scalar_one_or_none()

    if not addon_to_delete:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Addon not found."
        )
    
    if addon_to_delete.user_uuid != current_user_uuid:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not authorized to delete this addon."
        )
    
    session.delete(addon_to_delete)
    await session.commit()

    return Response(status_code=status.HTTP_204_NO_CONTENT)

@router.post("/addons/{addon_uuid}/download", status_code=status.HTTP_200_OK)
# @limiter.limit("100/day")
async def increment_download_count(
    addon_uuid: uuid.UUID,
    session: AsyncSession = Depends(get_session)
):
    db_addon = await session.execute(select(AddOn).where(AddOn.uuid == addon_uuid))
    addon_to_update = db_addon.scalar_one_or_none()

    if not addon_to_update:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Addon not found."
        )

    addon_to_update.downloads += 1

    await session.commit()
    await session.refresh(addon_to_update)

    return Response(status_code=status.HTTP_200_OK)