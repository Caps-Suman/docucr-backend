from sqlalchemy import Column, String, Text, DateTime, func, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from .module import Base
import uuid

class DocumentType(Base):
    __tablename__ = "document_types"
    __table_args__ = {'schema': 'docucr'}
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), nullable=False, unique=True)
    description = Column(Text, nullable=True)
    status_id = Column(String, ForeignKey('docucr.status.id'), nullable=False, default='active')
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    templates = relationship("Template", back_populates="document_type", cascade="all, delete-orphan")
    status = relationship("Status")
    
    def __repr__(self):
        return f"<DocumentType(id={self.id}, name='{self.name}')>"