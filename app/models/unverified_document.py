from sqlalchemy import Column, String, DateTime, ForeignKey, JSON, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
from .module import Base

class UnverifiedDocument(Base):
    __tablename__ = "unverified_documents"
    __table_args__ = {'schema': 'docucr'}
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(Integer, ForeignKey("docucr.documents.id"), nullable=False)
    
    suspected_type = Column(String(100), nullable=True) # Type name returned by AI
    page_range = Column(String(50), nullable=True)
    extracted_data = Column(JSON, nullable=True) # Preview data
    status = Column(String(20), default="PENDING") # PENDING, VERIFIED, REJECTED
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    document = relationship("Document", back_populates="unverified_documents")
