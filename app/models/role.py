from sqlalchemy import Column, String, Boolean, Text, DateTime, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .module import Base

class Role(Base):
    __tablename__ = "role"
    __table_args__ = (
    UniqueConstraint("name", "organisation_id", name="ux_role_name_org"),
    {"schema": "docucr"},
    )
   
    
    id = Column(String, primary_key=True, index=True)
    name = Column(String(50), nullable=False, index=True)
    description = Column(Text, nullable=True)
    status_id = Column(Integer, ForeignKey('docucr.status.id'), nullable=True)
    can_edit = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    created_by = Column(String, ForeignKey('docucr.user.id'), nullable=True)
    organisation_id = Column(String, ForeignKey('docucr.organisation.id'), nullable=True)
    
    status_relation = relationship("Status")
    user = relationship("User", foreign_keys=[created_by], primaryjoin="remote(User.id) == Role.created_by")
    
    users = relationship(
        "User",
        secondary="docucr.user_role",
        back_populates="roles",
        overlaps="user_roles,role_users,user,role"
    )

    organisations = relationship(
        "Organisation",
        secondary="docucr.organisation_role",
        back_populates="roles",
        overlaps="organisation_roles,role_organisations,organisation,role"
    )
