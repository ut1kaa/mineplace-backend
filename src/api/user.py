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
from src.models.user import User
from src.database import get_session
from src.models.user_likes import UserLike
from src.settings import settings
from .addon import AddOnListResponse, AddOnResponse

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/users/{user_uuid}/addons", response_model=AddOnListResponse, status_code=status.HTTP_200_OK)
async def get_user_addons(
    user_uuid: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(10, ge=1, le=100, description="Number of items per page"),
    type: Optional[AddOnType] = Query(None, description="Filter by type"),
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
    search: Optional[str] = Query(
        None,
        min_length=2,
        description="earch quer"
    )
):

    user_exists = await session.execute(select(User).where(User.uuid == user_uuid))
    user = user_exists.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    query_statement = select(
        AddOn,
        func.count(UserLike.uuid).label("likes_count")
    ).outerjoin(UserLike, AddOn.uuid == UserLike.addon_uuid).where(
        AddOn.user_uuid == user_uuid
    )


    
    if search:
        search_pattern = f"%{search.lower()}%"
        query_statement = query_statement.where(
            or_(
                func.lower(AddOn.name).like(search_pattern),
                func.lower(AddOn.short_description).like(search_pattern),
                func.lower(AddOn.description).like(search_pattern)
            )
        )

    if type:
        query_statement = query_statement.where(AddOn.type == type)

    subq = query_statement.group_by(AddOn.uuid).subquery()
    count_query = select(func.count()).select_from(subq)
    total_count_result = await session.execute(count_query)
    total_count = total_count_result.scalar_one()

    if sort_by:
        sort_column = getattr(AddOn, sort_by, None)
        if sort_column:
            if sort_order == "desc":
                query_statement = query_statement.order_by(desc(sort_column))
            else:
                query_statement = query_statement.order_by(asc(sort_column))
        elif sort_by == "likes_count":
            if sort_order == "desc":
                query_statement = query_statement.order_by(desc(func.count(UserLike.uuid)))
            else:
                query_statement = query_statement.order_by(asc(func.count(UserLike.uuid)))

    offset = (page - 1) * per_page
    query_statement = query_statement.offset(offset).limit(per_page)

    query_statement = query_statement.group_by(AddOn.uuid)

    result = await session.execute(query_statement)
    addon_rows = result.all()

    addons_response_list = []
    for db_addon, likes_count in addon_rows:
        addons_response_list.append(AddOnResponse.model_validate({
            "uuid": db_addon.uuid, "user_uuid": db_addon.user_uuid, "username": user.username, "name": db_addon.name,
            "type": db_addon.type, "short_description": db_addon.short_description,
            "description": db_addon.description, "downloads": db_addon.downloads,
            "publish_date": db_addon.publish_date, "update_date": db_addon.update_date,
            "likes_count": likes_count
        }))

    return AddOnListResponse(
        items=addons_response_list,
        total_count=total_count,
        page=page,
        per_page=per_page
    )

@router.get("/users/{user_uuid}/liked_addons", response_model=AddOnListResponse, status_code=status.HTTP_200_OK, dependencies=[Depends(authenticate)])
async def get_user_liked_addons(
    user_uuid: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(10, ge=1, le=100, description="Number of items per page"),
    sort_by: Optional[str] = Query(
        "publish_date",
        description="Filter by type",
        regex="^(name|publish_date|update_date|downloads|likes_count|relevance)$"
    ),
    sort_order: Optional[str] = Query(
        "desc",
        description="Sort order.",
        regex="^(asc|desc)$"
    ),
    search: Optional[str] = Query(
        None,
        min_length=2,
        description="Search query"
    )
):
    user_exists = await session.execute(select(User).where(User.uuid == user_uuid))
    if not user_exists.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    query_statement = select(
        AddOn,
        func.count(UserLike.uuid).label("likes_count")
    ).join(UserLike, AddOn.uuid == UserLike.addon_uuid) 
    
    query_statement = query_statement.where(UserLike.user_uuid == user_uuid)

    if search:
        search_pattern = f"%{search.lower()}%"
        query_statement = query_statement.where(
            or_(
                func.lower(AddOn.name).like(search_pattern),
                func.lower(AddOn.short_description).like(search_pattern),
                func.lower(AddOn.description).like(search_pattern)
            )
        )
    
    query_statement = query_statement.group_by(AddOn.uuid)

    count_query = select(func.count(distinct(AddOn.uuid))).select_from(
        query_statement.subquery()
    )
    total_count_result = await session.execute(count_query)
    total_count = total_count_result.scalar_one()

    if sort_by:
        sort_column = getattr(AddOn, sort_by, None)
        if sort_column:
            if sort_order == "desc": query_statement = query_statement.order_by(desc(sort_column))
            else: query_statement = query_statement.order_by(asc(sort_column))
        elif sort_by == "likes_count":
            if sort_order == "desc": query_statement = query_statement.order_by(desc(func.count(UserLike.uuid)))
            else: query_statement = query_statement.order_by(asc(func.count(UserLike.uuid)))

    offset = (page - 1) * per_page
    query_statement = query_statement.offset(offset).limit(per_page)

    result = await session.execute(query_statement)
    addon_rows = result.all()

    addons_response_list = []
    for db_addon, likes_count in addon_rows:
        addons_response_list.append(AddOnResponse.model_validate({
            "uuid": db_addon.uuid, "user_uuid": db_addon.user_uuid, "name": db_addon.name,
            "type": db_addon.type, "short_description": db_addon.short_description,
            "description": db_addon.description, "downloads": db_addon.downloads,
            "publish_date": db_addon.publish_date, "update_date": db_addon.update_date,
            "likes_count": likes_count
        }))

    return AddOnListResponse(
        items=addons_response_list,
        total_count=total_count,
        page=page,
        per_page=per_page
    )