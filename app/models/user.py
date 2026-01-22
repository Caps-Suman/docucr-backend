from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Integer
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
from .module import Base

class User(Base):
    __tablename__ = "user"
    __table_args__ = {'schema': 'docucr'}
    
    id = Column(String, primary_key=True, index=True)
    email = Column(String, unique=True, nullable=False, index=True)
    username = Column(String, unique=True, nullable=False, index=True)
    hashed_password = Column(String, nullable=False)
    first_name = Column(String, nullable=True)
    middle_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)
    phone_country_code = Column(String(5), nullable=True)
    phone_number = Column(String(15), nullable=True)
    is_superuser = Column(Boolean, default=False)
    is_supervisor = Column(Boolean, default=False)
    is_client = Column(Boolean, default=False)
    client_id = Column(UUID(as_uuid=True), ForeignKey('docucr.client.id'), nullable=True)
    status_id = Column(Integer, ForeignKey('docucr.status.id'), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    documents = relationship("Document", back_populates="user")
    status_relation = relationship("Status")
    roles = relationship(
    "Role",
    secondary="docucr.user_role",
    backref="users",
    lazy="selectin",          # ✅ NOT joined
    overlaps="users,user_roles,role"  # ✅ silence conflict properly
)
