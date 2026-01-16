from sqlalchemy import Column, String, Text, DateTime
from sqlalchemy.sql import func
from .module import Base

class Privilege(Base):
    __tablename__ = "privilege"
    __table_args__ = {'schema': 'docucr'}
    
    id = Column(String, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False, index=True)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
