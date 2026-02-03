from sqlalchemy import Column, String, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import UUID
from .module import Base

class UserClient(Base):
    __tablename__ = "user_client"
    __table_args__ = (
        UniqueConstraint("user_id", "client_id", name="uq_user_client"),
        {"schema": "docucr"}
    )

    id = Column(String, primary_key=True, index=True)
    user_id = Column(String, ForeignKey("docucr.user.id"), nullable=False)
    client_id = Column(UUID(as_uuid=True), ForeignKey("docucr.client.id"), nullable=False)
    assigned_by = Column(String, ForeignKey("docucr.user.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

