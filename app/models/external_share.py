from sqlalchemy import Column, String, DateTime, ForeignKey, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .module import Base
import uuid

class ExternalShare(Base):
    __tablename__ = "external_shares"
    __table_args__ = {'schema': 'docucr'}
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(Integer, ForeignKey('docucr.documents.id'), nullable=False)
    email = Column(String, nullable=False)
    password_hash = Column(String, nullable=False)
    token = Column(String, unique=True, nullable=False, index=True)
    shared_by = Column(String, ForeignKey('docucr.user.id'), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    document = relationship("Document")
    shared_by_user = relationship("User", foreign_keys=[shared_by])
