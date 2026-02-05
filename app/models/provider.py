from datetime import datetime
from sqlalchemy import Column, String, Boolean, DateTime, Text, ForeignKey, Integer, CheckConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import UUID
from .module import Base
import uuid
class Provider(Base):
    __tablename__ = "provider"
    __table_args__ = (
        CheckConstraint(
            "zip_code ~ '^[0-9]{5}-[0-9]{4}$'",
            name="ck_client_zip_9_digit"
        ),
        CheckConstraint("char_length(state_code) = 2", name="ck_client_state_code_len"),
        {'schema': 'docucr'}
    )

    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    client_id = Column(UUID, ForeignKey("docucr.client.id"), nullable=False)
    location_id = Column(UUID, ForeignKey("docucr.client_location.id"), nullable=True)
    created_by=Column(String, nullable=True)
    first_name = Column(String, nullable=False)
    middle_name = Column(String)
    last_name = Column(String)
    npi = Column(String)
    
    # --- Address ---
    address_line_1 = Column(String(250), nullable=True)
    address_line_2 = Column(String(250), nullable=True)
    city=Column(String(250), nullable=True)
    state_code = Column(String(2), nullable=True)        # e.g. VA, CA
    state_name = Column(String(50), nullable=True)       # e.g. Virginia
    country = Column(String(50), nullable=True, default="United States")
    zip_code = Column(String(10), nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)

