from typing import TYPE_CHECKING, List
from sqlalchemy import Column, ForeignKey, Integer, String, DateTime, Text, Enum as SQLEnum
from sqlalchemy.orm import relationship, Mapped
from . import Base
from sqlalchemy.dialects.postgresql import UUID as UUID_TYPE
import uuid as UUID
import datetime
from enum import Enum as PyEnum

class AddOnType(PyEnum):
    Mod = 'mod'
    ResourcePack = 'resource_pack'
    DataPack = 'data_pack'
    Shader = 'shader'
    Plugins = 'plugins'

if TYPE_CHECKING:
    from .user import User
    from .user_likes import UserLike
    from .versions import Version

class AddOn(Base):
    __tablename__ = 'addons'

    uuid: Mapped[UUID.UUID] = Column(UUID_TYPE(as_uuid=True), primary_key=True, default=UUID.uuid4)
    user_uuid: Mapped[UUID.UUID] = Column(UUID_TYPE(as_uuid=True), ForeignKey('users.uuid'), nullable=False)
    name: Mapped[str] = Column(String(128), nullable=False, unique=True)
    type: Mapped[AddOnType] = Column(SQLEnum(AddOnType), nullable=False)
    short_description: Mapped[str] = Column(String(256), nullable=False)
    description: Mapped[str] = Column(Text, nullable=False)
    downloads: Mapped[int] = Column(Integer, nullable=False, default=0)
    publish_date: Mapped[datetime.datetime] = Column(DateTime(timezone=True), nullable=False, default=datetime.datetime.now(datetime.UTC))
    update_date: Mapped[datetime.datetime] = Column(DateTime(timezone=True), nullable=False, default=datetime.datetime.now(datetime.UTC), onupdate=datetime.datetime.now(datetime.UTC))

    user: Mapped['User'] = relationship('User', back_populates='addons')
    likes: Mapped[List['UserLike']] = relationship('UserLike', back_populates='addon', cascade='all, delete-orphan')
    versions: Mapped[List['Version']] = relationship('Version', back_populates='addon', cascade='all, delete-orphan')


    def __repr__(self) -> str:
        return f"<AddOn(uuid='{self.uuid}', name='{self.name}', short_description='{self.short_description}', description='{self.description}', publish_date='{self.publish_date}', update_date='{self.update_date}')>"

    def to_dict(self) -> dict:
        return {
            'uuid': str(self.uuid),
            'user_uuid': str(self.user_uuid),
            'name': self.name,
            'short_description': self.short_description,
            'description': self.description,
            'publish_date': self.publish_date.isoformat(),
            'update_date': self.update_date.isoformat()
        }