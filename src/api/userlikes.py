import datetime
import logging
from typing import Annotated, Optional
from slowapi.util import get_ipaddr
from uuid import UUID
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import JSONResponse
# from slowapi import Limiter
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

# limiter = Limiter(key_func=get_ipaddr, storage_uri="memory://")


@router.post("/addons/{addon_uuid}/like", status_code=status.HTTP_201_CREATED, dependencies=[Depends(authenticate)])
# @limiter.limit("100/day")
async def like_addon(
    addon_uuid: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    Authorize: AuthJWT = Depends()
):
    current_user_uuid = UUID(Authorize.get_jwt_subject())

    addon_exists = await session.execute(select(AddOn.uuid).where(AddOn.uuid == addon_uuid))
    if not addon_exists.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Addon not found.")

    existing_like = await session.execute(
        select(UserLike).where(
            UserLike.user_uuid == current_user_uuid,
            UserLike.addon_uuid == addon_uuid
        )
    )
    if existing_like.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You've already given this addon a like.")

    new_like = UserLike(user_uuid=current_user_uuid, addon_uuid=addon_uuid)
    
    try:
        session.add(new_like)
        await session.commit()
        await session.refresh(new_like)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to like.")

    return Response(status_code=status.HTTP_200_OK)

@router.delete("/addons/{addon_uuid}/like", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(authenticate)])
async def unlike_addon(
    addon_uuid: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    Authorize: AuthJWT = Depends()
):
    current_user_uuid = UUID(Authorize.get_jwt_subject())

    addon_exists = await session.execute(select(AddOn.uuid).where(AddOn.uuid == addon_uuid))
    if not addon_exists.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Addon not found.")

    like_to_delete = await session.execute(
        select(UserLike).where(
            UserLike.user_uuid == current_user_uuid,
            UserLike.addon_uuid == addon_uuid
        )
    )
    db_like = like_to_delete.scalar_one_or_none()

    if not db_like:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You didn't give this addon a like.")

    try:
        session.delete(db_like)
        await session.commit()
    except Exception:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to unlike.")

    return Response(status_code=status.HTTP_204_NO_CONTENT)
@router.get("/addons/{addon_uuid}/likes/count", status_code=status.HTTP_200_OK)
async def get_addon_likes_count(
    addon_uuid: uuid.UUID,
    session: AsyncSession = Depends(get_session)
):
    addon_exists = await session.execute(select(AddOn.uuid).where(AddOn.uuid == addon_uuid))
    if not addon_exists.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Addon not found.")
    
    likes_count_result = await session.execute(
        select(func.count(UserLike.uuid)).where(UserLike.addon_uuid == addon_uuid)
    )
    likes_count = likes_count_result.scalar_one()

    return {"likes_count": likes_count}