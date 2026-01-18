from sqlalchemy import Column, String, DateTime, ForeignKey, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .module import Base
import uuid

class DocumentShare(Base):
    __tablename__ = "document_shares"
    __table_args__ = {'schema': 'docucr'}
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(Integer, ForeignKey('docucr.documents.id'), nullable=False)
    user_id = Column(String, ForeignKey('docucr.user.id'), nullable=False)
    shared_by = Column(String, ForeignKey('docucr.user.id'), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    document = relationship("Document")
    user = relationship("User", foreign_keys=[user_id])
    shared_by_user = relationship("User", foreign_keys=[shared_by])