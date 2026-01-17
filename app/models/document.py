from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey
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
    status_id = Column(String, ForeignKey("docucr.status.id"), nullable=False)
    upload_progress = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)
    user_id = Column(String, ForeignKey("docucr.user.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    user = relationship("User", back_populates="documents")
    status = relationship("Status")