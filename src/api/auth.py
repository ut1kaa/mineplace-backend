import logging
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from fastapi_jwt_auth import AuthJWT
from pydantic import BaseModel, EmailStr, Field, field_validator
from src.middlewares.auth import authenticate
from src.models.user import User
from src.database import get_session
from src.settings import settings
import re

logger = logging.getLogger(__name__)

router = APIRouter()

class RegisterModel(BaseModel):
    """Model for user registration."""
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(..., min_length=settings.MIN_PASSWORD_LENGTH, max_length=settings.MAX_PASSWORD_LENGTH)

    @field_validator('username')
    @classmethod
    def validate_username(cls, v: str):
        """Validate username format."""
        if not re.match(r'^[a-zA-Z0-9_-]+$', v):
            raise ValueError('Username can only contain letters, numbers, underscores and dashes')
        return v.strip()

    @field_validator('email')
    @classmethod
    def validate_email(cls, v: EmailStr):
        """Validate email format."""
        return v.strip().lower()

    @field_validator('password')
    @classmethod
    def validate_password(cls, v: str):
        """Validate password strength."""
        if not re.match(settings.PASSWORD_REGEX, v):
            raise ValueError('Password must contain at least one letter and one number')
        return v

class LoginModel(BaseModel):
    """Model for user login."""
    email: EmailStr
    password: str

    @field_validator('email')
    @classmethod
    def validate_email(cls, v: EmailStr):
        """Validate email format."""
        return v.strip().lower()

class TokenResponse(BaseModel):
    """Model for token response."""
    token: str
    message: str

@router.post("/registration", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(
    user: RegisterModel,
    db: AsyncSession = Depends(get_session),
    Authorize: AuthJWT = Depends()
):
    """
    Register a new user.
    
    Args:
        user: User registration data
        db: Database session
        Authorize: JWT authorization
        
    Returns:
        TokenResponse: Access token and success message
        
    Raises:
        HTTPException: If email or username already exists
    """
    try:
        # Check for existing email
        result_email = await db.execute(select(User).filter(User.email == user.email))
        if result_email.scalars().first():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )
        
        # Check for existing username
        result_username = await db.execute(select(User).filter(User.username == user.username))
        if result_username.scalars().first():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username already registered"
            )

        # Create new user
        new_user = User(
            email=user.email,
            password=user.password,
            username=user.username
        )
        
        db.add(new_user)
        await db.commit()
        await db.refresh(new_user)

        # Create access token
        access_token = Authorize.create_access_token(subject=str(new_user.uuid))
        
        logger.info(f"New user registered: {new_user.email}")
        return TokenResponse(
            token=access_token,
            message="User registered successfully"
        )
        
    except Exception as e:
        logger.error(f"Registration failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Registration failed"
        )

@router.post("/authorization", response_model=TokenResponse)
async def login(
    user: LoginModel,
    db: AsyncSession = Depends(get_session),
    Authorize: AuthJWT = Depends()
):
    """
    Authenticate user and return access token.
    
    Args:
        user: User login data
        db: Database session
        Authorize: JWT authorization
        
    Returns:
        TokenResponse: Access token and success message
        
    Raises:
        HTTPException: If credentials are invalid
    """
    try:
        # Find user by email
        result = await db.execute(select(User).filter(User.email == user.email))
        db_user = result.scalars().first()

        # Validate credentials
        if not db_user or not db_user.check_password(user.password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials"
            )

        # Create access token
        access_token = Authorize.create_access_token(subject=str(db_user.uuid))
        
        logger.info(f"User logged in: {db_user.email}")
        return TokenResponse(
            token=access_token,
            message="Login successful"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Login failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Login failed"
        )

@router.post("/logout", status_code=status.HTTP_200_OK, dependencies=[Depends(authenticate)])
async def logout(Authorize: AuthJWT = Depends()):
    """
    Logout user by invalidating JWT token.
    
    Args:
        Authorize: JWT authorization
        
    Returns:
        dict: Success message
    """
    try:
        Authorize.unset_jwt_cookies()
        logger.info("User logged out successfully")
        return {"message": "Logout successful"}
    except Exception as e:
        logger.error(f"Logout failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Logout failed"
        )

@router.get("/me", response_model=dict, dependencies=[Depends(authenticate)])
async def get_current_user(
    Authorize: AuthJWT = Depends(),
    db: AsyncSession = Depends(get_session)
):
    """
    Get current user information.
    
    Args:
        Authorize: JWT authorization
        db: Database session
        
    Returns:
        dict: User information
        
    Raises:
        HTTPException: If user not found
    """
    try:
        user_id = UUID(Authorize.get_jwt_subject()) 
        result = await db.execute(select(User).filter(User.uuid == user_id))
        user = result.scalars().first()
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
            
        return user.to_dict()
        
    except Exception as e:
        logger.error(f"Failed to get user info: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get user information"
        )