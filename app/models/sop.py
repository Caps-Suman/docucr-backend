from sqlalchemy import Column, String, DateTime, ForeignKey, Text, Integer
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from .module import Base
import uuid

class SOP(Base):
    __tablename__ = "sop"
    __table_args__ = {'schema': 'docucr'}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    title = Column(String, nullable=False)
    category = Column(String, nullable=False)
    provider_type = Column(String, nullable=False)  # 'new' or 'existing'
    
    # Relationship to Client if provider_type is 'existing'
    client_id = Column(UUID(as_uuid=True), ForeignKey('docucr.client.id'), nullable=True)
    
    # JSONB fields for flexible data structures
    provider_info = Column(JSONB, nullable=True)
    workflow_process = Column(JSONB, nullable=True)
    billing_guidelines = Column(JSONB, nullable=True)
    coding_rules = Column(JSONB, nullable=True)
    
    status_id = Column(Integer, ForeignKey('docucr.status.id'), nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    client = relationship("Client", backref="sops")
    status = relationship("Status")
