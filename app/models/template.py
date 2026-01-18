from sqlalchemy import Column, String, Text, DateTime, func, ForeignKey, JSON, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from .module import Base
import uuid

class Template(Base):
    __tablename__ = "templates"
    __table_args__ = {'schema': 'docucr'}
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    template_name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    document_type_id = Column(UUID(as_uuid=True), ForeignKey('docucr.document_types.id'), nullable=False)
    status_id = Column(Integer, ForeignKey('docucr.status.id'), nullable=False)
    extraction_fields = Column(JSON, nullable=True, default=list)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    document_type = relationship("DocumentType", back_populates="templates")
    status = relationship("Status")
    
    def __repr__(self):
        return f"<Template(id={self.id}, name='{self.template_name}')>"