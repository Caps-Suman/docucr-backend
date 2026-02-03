from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from datetime import datetime
from .module import Base

class DocumentListConfig(Base):
    __tablename__ = "document_list_configs"
    __table_args__ = {'schema': 'docucr'}
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, ForeignKey("docucr.user.id"), nullable=False, unique=True)
    configuration = Column(JSONB, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    user = relationship("User")
