from sqlalchemy import Column, String, Boolean, DateTime, Text, ForeignKey, Integer, CheckConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import UUID
from .module import Base
import uuid

class Client(Base):
    __tablename__ = "client"
    __table_args__ = (
        CheckConstraint(
            "zip_code ~ '^[0-9]{5}-[0-9]{4}$'",
            name="ck_client_zip_9_digit"
        ),
        CheckConstraint("char_length(state_code) = 2", name="ck_client_state_code_len"),
        {'schema': 'docucr'}
    )


    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)

    # --- Identity ---
    business_name = Column(String(255), nullable=True)
    first_name = Column(String(100), nullable=True)
    middle_name = Column(String(100), nullable=True)
    last_name = Column(String(100), nullable=True)

    # --- Provider ---
    npi = Column(String(10), nullable=True, index=True)  # NPI is 10 digits
    type = Column(String(50), nullable=True)

    # --- Address ---
    address_line_1 = Column(String(250), nullable=True)
    address_line_2 = Column(String(250), nullable=True)
    city=Column(String(250), nullable=True)
    state_code = Column(String(2), nullable=True)        # e.g. VA, CA
    state_name = Column(String(50), nullable=True)       # e.g. Virginia
    country = Column(String(50), nullable=True, default="United States")
    zip_code = Column(String(10), nullable=True)

    # --- System ---
    is_user = Column(Boolean, default=False)
    created_by = Column(String, ForeignKey('docucr.user.id'), nullable=True)
    
    @property
    def user_id(self):
        import traceback
        print("DEBUG: Client.user_id ACCESS DETECTED!")
        traceback.print_stack()
        return self.created_by
    
    @user_id.setter
    def user_id(self, value):
        import traceback
        print(f"DEBUG: Client.user_id SETTING DETECTED: {value}")
        traceback.print_stack()
        self.created_by = value
    status_id = Column(Integer, ForeignKey('docucr.status.id'), nullable=True)
    description = Column(Text, nullable=True)

    deleted_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    status_relation = relationship("Status")

    @property
    def statusCode(self):
        return self.status_relation.code if self.status_relation else None

    @property
    def status_code(self):
        return self.statusCode

    @property
    def assigned_users(self):
        return [f"{u.first_name} {u.last_name}" for u in self.users]
