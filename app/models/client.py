from sqlalchemy import Column, String, Boolean, DateTime, Text, ForeignKey, Integer
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import UUID
from .module import Base
import uuid

class Client(Base):
    __tablename__ = "client"
    __table_args__ = {'schema': 'docucr'}
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    business_name = Column(String, nullable=True)
    first_name = Column(String, nullable=True)
    middle_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)
    npi = Column(String, nullable=True, index=True)
    is_user = Column(Boolean, default=False)
    user_id = Column(String, ForeignKey('docucr.user.id'), nullable=True)
    type = Column(String, nullable=True)
    status_id = Column(Integer, ForeignKey('docucr.status.id'), nullable=True)
    description = Column(Text, nullable=True)
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    status_relation = relationship("Status")

    @property
    def statusCode(self):
        return self.status_relation.code if self.status_relation else None

    @property
    def assigned_users(self):
        return [f"{u.first_name} {u.last_name}" for u in self.users]
