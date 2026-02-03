from sqlalchemy import Column, String, ForeignKey, DateTime
from sqlalchemy.sql import func
from .module import Base
from sqlalchemy.orm import relationship, backref

class UserRole(Base):
    __tablename__ = "user_role"
    __table_args__ = {'schema': 'docucr'}
    
    id = Column(String, primary_key=True, index=True)
    user_id = Column(String, ForeignKey('docucr.user.id'), nullable=False)
    role_id = Column(String, ForeignKey('docucr.role.id'), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    user = relationship("User", backref=backref("user_roles", overlaps="users,roles"), overlaps="users,roles")
    role = relationship("Role", backref=backref("role_users", overlaps="users,roles"), overlaps="users,roles")