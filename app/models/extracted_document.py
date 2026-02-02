from sqlalchemy import Column, String, DateTime, ForeignKey, JSON, Float, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
from .module import Base

class ExtractedDocument(Base):
    __tablename__ = "extracted_documents"
    __table_args__ = {'schema': 'docucr'}
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(Integer, ForeignKey("docucr.documents.id"), nullable=False)
    document_type_id = Column(UUID(as_uuid=True), ForeignKey("docucr.document_types.id"), nullable=False)
    template_id = Column(UUID(as_uuid=True), ForeignKey("docucr.templates.id"), nullable=True)
    
    page_range = Column(String(50), nullable=True) # e.g., "1-3"
    extracted_data = Column(JSON, nullable=True)
    confidence = Column(Float, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    document = relationship("Document", back_populates="extracted_documents")
    document_type = relationship("DocumentType")
    template = relationship("Template")
