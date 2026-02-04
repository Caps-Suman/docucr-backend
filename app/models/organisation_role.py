from sqlalchemy import Column, String, ForeignKey, DateTime
from sqlalchemy.sql import func
from .module import Base
from sqlalchemy.orm import relationship, backref

class OrganisationRole(Base):
    __tablename__ = "organisation_role"
    __table_args__ = {'schema': 'docucr'}
    
    id = Column(String, primary_key=True, index=True)
    organisation_id = Column(String, ForeignKey('docucr.organisation.id'), nullable=False)
    role_id = Column(String, ForeignKey('docucr.role.id'), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    organisation = relationship("Organisation", backref=backref("organisation_roles", cascade="all, delete-orphan"))
    role = relationship("Role", backref=backref("role_organisations", cascade="all, delete-orphan"))
