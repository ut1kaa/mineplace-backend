import datetime
from typing import TYPE_CHECKING, List
from sqlalchemy import Column, Integer, String, DateTime, Boolean
from sqlalchemy.orm import relationship, Mapped
from . import Base
from werkzeug.security import generate_password_hash, check_password_hash
from src.settings import settings
import uuid as UUID
from sqlalchemy.dialects.postgresql import UUID as UUID_TYPE

if TYPE_CHECKING:
    from .addon import AddOn
    from .user_likes import UserLike

class User(Base):
    """User model for authentication and user management."""
    
    __tablename__ = 'users'

    uuid: Mapped[UUID.UUID] = Column(UUID_TYPE(as_uuid=True), primary_key=True, default=UUID.uuid4)
    username: Mapped[str] = Column(String(255), unique=True, nullable=False, index=True)
    email: Mapped[str] = Column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = Column(String(255), nullable=False)
    profile_picture: Mapped[str] = Column(String(50), nullable=True)
    created_at: Mapped[datetime.datetime] = Column(DateTime(timezone=True), default=datetime.datetime.now(datetime.UTC), nullable=False)

    addons: Mapped['AddOn'] = relationship('AddOn', back_populates='user', cascade='all, delete-orphan')
    likes: Mapped[List['UserLike']] = relationship('UserLike', back_populates='user', cascade='all, delete-orphan')

    def __init__(self, username, email, password):
        self.username = username
        self.email = email
        self.set_password(password)

    def set_password(self, password: str) -> None:
        """
        Set the user's password.
        
        Args:
            password: The password to set
        """
        if len(password) < settings.MIN_PASSWORD_LENGTH:
            raise ValueError(f"Password must be at least {settings.MIN_PASSWORD_LENGTH} characters long")
        if len(password) > settings.MAX_PASSWORD_LENGTH:
            raise ValueError(f"Password must be at most {settings.MAX_PASSWORD_LENGTH} characters long")
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        """
        Check if the provided password matches the user's password.
        
        Args:
            password: The password to check
            
        Returns:
            bool: True if the password matches, False otherwise
        """
        return check_password_hash(self.password_hash, password)

    def __repr__(self) -> str:
        """String representation of the user."""
        return f"<User(username={self.username}, email={self.email})>"

    def to_dict(self) -> dict:
        """
        Convert user object to dictionary.
        
        Returns:
            dict: User data as dictionary
        """
        return {
            'uuid': self.uuid,
            'username': self.username,
            'email': self.email,
            'profile_picture': self.profile_picture,
            'created_at': self.created_at.isoformat(),
        }
