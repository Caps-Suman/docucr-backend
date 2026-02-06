from datetime import datetime
from sqlalchemy import Column, String, ForeignKey, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from .module import Base
import uuid

class ProviderClientMapping(Base):
    __tablename__ = "provider_client_mapping"
    __table_args__ = {'schema': 'docucr'}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    provider_id = Column(UUID(as_uuid=True), ForeignKey("docucr.provider.id"), nullable=False)
    client_id = Column(UUID(as_uuid=True), ForeignKey("docucr.client.id"), nullable=False)
    location_id = Column(UUID(as_uuid=True), ForeignKey("docucr.client_location.id"), nullable=True)
    created_by = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
