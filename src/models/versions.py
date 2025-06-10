from typing import TYPE_CHECKING
from sqlalchemy import Column, ForeignKey, Integer, String, DateTime, Text, Enum as SQLEnum
from sqlalchemy.orm import relationship, Mapped
from . import Base
from sqlalchemy.dialects.postgresql import UUID as UUID_TYPE
import uuid as UUID
import datetime
from enum import Enum as PyEnum

if TYPE_CHECKING:
    from .addon import AddOn

class Version(Base):
    __tablename__ = 'versions'

    uuid: Mapped[UUID.UUID] = Column(UUID_TYPE, primary_key=True, default=UUID.uuid4)
    addon_uuid: Mapped[UUID.UUID] = Column(UUID_TYPE, ForeignKey('addons.uuid'), nullable=False)
    version: Mapped[str] = Column(String(64), nullable=False)
    description: Mapped[str] = Column(Text, nullable=True)
    download_url: Mapped[str] = Column(String, nullable=False)
    file_hash: Mapped[str] = Column(String(64), nullable=False)
    created_at: Mapped[datetime.datetime] = Column(DateTime(timezone=True), nullable=False, default=datetime.datetime.now(datetime.UTC))

    addon: Mapped['AddOn'] = relationship('AddOn', back_populates='versions')

    def __repr__(self) -> str:
         return f"<Version(uuid='{self.uuid}', addon_uuid='{self.addon_uuid}', version='{self.version}', description='{self.description}', download_url='{self.download_url}', file_hash='{self.file_hash}', created_at='{self.created_at}')>"
    
    def to_dict(self) -> dict:
        return {
            'uuid': self.uuid,
            'addon_uuid': self.addon_uuid,
            'version': self.version,
            'description': self.description,
            'download_url': self.download_url,
            'file_hash': self.file_hash,
            'created_at': self.created_at.isoformat(),
        }