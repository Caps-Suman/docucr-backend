from sqlalchemy import Column, String, ForeignKey, DateTime
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from .module import Base

class RoleSubmodule(Base):
    __tablename__ = "role_submodule"
    __table_args__ = {'schema': 'docucr'}
    
    id = Column(String, primary_key=True, index=True)
    role_id = Column(String, ForeignKey('docucr.role.id'), nullable=False)
    submodule_id = Column(String, ForeignKey('docucr.submodule.id'), nullable=False)
    privilege_id = Column(String, ForeignKey('docucr.privilege.id'), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    submodule = relationship("Submodule", back_populates="role_submodules")
    role = relationship("Role")
    privilege = relationship("Privilege")
