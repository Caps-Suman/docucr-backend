from sqlalchemy import Column, String, Text, DateTime
from sqlalchemy.sql import func
from .module import Base

class Status(Base):
    __tablename__ = "status"
    __table_args__ = {'schema': 'docucr'}
    
    id = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False, index=True)
    description = Column(Text, nullable=True)
    type = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
