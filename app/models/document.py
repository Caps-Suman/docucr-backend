from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, Boolean, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime
from .module import Base

class Document(Base):
    __tablename__ = "documents"
    __table_args__ = {'schema': 'docucr'}
    
    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String(255), nullable=False)
    original_filename = Column(String(255), nullable=False)
    file_size = Column(Integer, nullable=False)
    content_type = Column(String(100), nullable=False)
    s3_key = Column(String(500), nullable=True)
    s3_bucket = Column(String(100), nullable=True)
    status_id = Column(Integer, ForeignKey("docucr.status.id"), nullable=False)
    upload_progress = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)
    user_id = Column(String, ForeignKey("docucr.user.id"), nullable=False)
    analysis_report_s3_key = Column(String(500), nullable=True)
    is_archived = Column(Boolean, default=False, nullable=False)
    total_pages = Column(Integer, default=0)
    created_at = Column(
    DateTime(timezone=True),
    server_default=func.now(),
    nullable=False
    )

    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )

    
    user = relationship("User", back_populates="documents")
    status = relationship("Status")
    
    # New Columns for Processing Context
    document_type_id = Column(UUID(as_uuid=True), ForeignKey("docucr.document_types.id"), nullable=True)
    template_id = Column(UUID(as_uuid=True), ForeignKey("docucr.templates.id"), nullable=True)
    enable_ai = Column(Boolean, default=False)

    # Relationships to new tables
    extracted_documents = relationship("ExtractedDocument", back_populates="document", cascade="all, delete-orphan")
    unverified_documents = relationship("UnverifiedDocument", back_populates="document", cascade="all, delete-orphan")
    
    # metadata relationship
    form_data_relation = relationship("DocumentFormData", back_populates="document", uselist=False, cascade="all, delete-orphan")