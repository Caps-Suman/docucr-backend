from sqlalchemy import Column, String, Boolean, DateTime, JSON, ForeignKey
from sqlalchemy.sql import func
from .module import Base
import uuid

class Webhook(Base):
    __tablename__ = "webhook"
    __table_args__ = {'schema': 'docucr'}
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()), index=True)
    user_id = Column(String, ForeignKey('docucr.user.id'), nullable=False)
    name = Column(String(100), nullable=False)
    url = Column(String(500), nullable=False)
    secret = Column(String(255), nullable=True) # For signature verification
    events = Column(JSON, nullable=False, default=list) # List of events like ['document.uploaded']
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
