from sqlalchemy import Column, String, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.sql import func
from .module import Base

class Client(Base):
    __tablename__ = "client"
    __table_args__ = {'schema': 'docucr'}
    
    id = Column(String, primary_key=True, index=True)
    business_name = Column(String, nullable=True)
    first_name = Column(String, nullable=True)
    middle_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)
    npi = Column(String, nullable=True, index=True)
    is_user = Column(Boolean, default=False)
    type = Column(String, nullable=True)
    status_id = Column(String, ForeignKey('docucr.status.id'), nullable=True)
    description = Column(Text, nullable=True)
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
