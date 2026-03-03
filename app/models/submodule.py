from sqlalchemy import Column, String, Integer, ForeignKey, DateTime
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from .module import Base

class Submodule(Base):
    __tablename__ = "submodule"
    __table_args__ = {'schema': 'docucr'}
    
    id = Column(String, primary_key=True, index=True)
    module_id = Column(String, ForeignKey('docucr.module.id'), nullable=False)
    name = Column(String, nullable=False)
    label = Column(String, nullable=False)
    route_key = Column(String, nullable=False)
    display_order = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    module = relationship("Module", back_populates="submodules_list")
    role_submodules = relationship("RoleSubmodule", back_populates="submodule")
