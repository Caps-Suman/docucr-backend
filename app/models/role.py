from sqlalchemy import Column, String, Boolean, Text, DateTime, ForeignKey, Integer
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .module import Base

class Role(Base):
    __tablename__ = "role"
    __table_args__ = {'schema': 'docucr'}
    
    id = Column(String, primary_key=True, index=True)
    name = Column(String(50), unique=True, nullable=False, index=True)
    description = Column(Text, nullable=True)
    status_id = Column(Integer, ForeignKey('docucr.status.id'), nullable=True)
    can_edit = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    user_id = Column(String, ForeignKey('docucr.user.id'), nullable=True)
    
    status_relation = relationship("Status")
    user = relationship("User", foreign_keys=[user_id])
    
    users = relationship(
        "User",
        secondary="docucr.user_role",
        back_populates="roles",
        overlaps="user_roles,role_users,user,role"
    )
