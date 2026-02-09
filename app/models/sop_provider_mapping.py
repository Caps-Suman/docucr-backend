from datetime import datetime
from sqlalchemy import Column, String, ForeignKey, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from .module import Base
import uuid

class SopProviderMapping(Base):
    __tablename__ = "sop_provider_mapping"
    __table_args__ = {'schema': 'docucr'}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    sop_id = Column(UUID(as_uuid=True), ForeignKey("docucr.sop.id"), nullable=False)
    provider_id = Column(UUID(as_uuid=True), ForeignKey("docucr.provider.id"), nullable=False)
    created_by = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
