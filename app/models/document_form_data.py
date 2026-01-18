from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from datetime import datetime
from uuid import uuid4
from sqlalchemy.dialects.postgresql import UUID
from .module import Base

class DocumentFormData(Base):
    __tablename__ = "document_form_data"
    __table_args__ = {'schema': 'docucr'}

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("docucr.documents.id"), unique=True, nullable=False)
    form_id = Column(String, ForeignKey("docucr.form.id"), nullable=True)
    data = Column(JSONB, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    document = relationship("Document", back_populates="form_data_relation")
    form = relationship("Form")
