from datetime import datetime
from sqlalchemy import Column, String, Boolean, DateTime, Text, ForeignKey, Integer, CheckConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import UUID
from .module import Base
import uuid

class ClientLocation(Base):
    __tablename__ = "client_location"
    __table_args__ = {'schema': 'docucr'}
    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    client_id = Column(UUID, ForeignKey("docucr.client.id"), nullable=False)
    created_by = Column(String, nullable=True)
    address_line_1 = Column(String, nullable=False)
    address_line_2 = Column(String)
    city = Column(String, nullable=False)
    state_code = Column(String, nullable=False)
    state_name = Column(String)
    country = Column(String, default="United States")
    zip_code = Column(String, nullable=False)

    is_primary = Column(Boolean, default=False)
