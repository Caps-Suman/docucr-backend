from datetime import datetime
from sqlalchemy import Column, String, Boolean, DateTime, Text, ForeignKey, Integer, CheckConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import UUID
from .module import Base
import uuid

class ProviderClientMap(Base):
    __tablename__ = "provider_client_map"

    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    provider_id = Column(UUID, ForeignKey("providers.id"))
    client_id = Column(UUID, ForeignKey("clients.id"))
    location_id = Column(UUID, ForeignKey("client_locations.id"))
