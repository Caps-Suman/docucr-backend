from sqlalchemy import Column, String, Integer, DateTime, Boolean
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import UUID
from .module import Base
import uuid

class Printer(Base):
    __tablename__ = "printer"
    __table_args__ = {'schema': 'docucr'}
    
    id = Column(String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False)
    ip_address = Column(String, nullable=False)
    port = Column(Integer, default=9100, nullable=False)
    protocol = Column(String, default="RAW", nullable=False) # RAW, IPP, LPD
    description = Column(String, nullable=True)
    status = Column(String, default="ACTIVE") # ACTIVE, INACTIVE, ERROR
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
