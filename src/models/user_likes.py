from typing import TYPE_CHECKING
from sqlalchemy import Column, ForeignKey, UniqueConstraint, DateTime
from sqlalchemy.orm import relationship, Mapped
from . import Base
from sqlalchemy.dialects.postgresql import UUID as UUID_TYPE
import uuid as UUID
import datetime
from enum import Enum as PyEnum

if TYPE_CHECKING: 
    from .addon import AddOn
    from .user import User

class UserLike(Base):
    __tablename__ = "user_likes"

    __table_args__ = (UniqueConstraint('user_uuid', 'addon_uuid', name='_user_addon_uc'),)

    uuid: Mapped[UUID.UUID] = Column(UUID_TYPE(as_uuid=True), primary_key=True, default=UUID.uuid4)
    user_uuid: Mapped[UUID.UUID] = Column(UUID_TYPE(as_uuid=True), ForeignKey('users.uuid'), nullable=False)
    addon_uuid: Mapped[UUID.UUID] = Column(UUID_TYPE(as_uuid=True), ForeignKey('addons.uuid'), nullable=False)
    created_at: Mapped[datetime.datetime] = Column(DateTime(timezone=True), default=datetime.datetime.now(datetime.UTC))

    user: Mapped['User'] = relationship("User", back_populates="likes")
    addon: Mapped['AddOn'] = relationship("AddOn", back_populates="likes")

    def __repr__(self) -> str:
        return f"<UserLike(uuid='{self.uuid}' user_uuid='{self.user_uuid}' addon_uuid='{self.addon_uuid}', created_at='{self.created_at}')>"
    
    def to_dict(self) -> dict:
        return {
            "uuid": str(self.uuid),
            "user_uuid": str(self.user_uuid),
            "addon_uuid": str(self.addon_uuid),
            "created_at": self.created_at.isoformat(),
        }