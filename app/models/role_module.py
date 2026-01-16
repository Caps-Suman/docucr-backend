from sqlalchemy import Column, String, ForeignKey, DateTime
from sqlalchemy.sql import func
from .module import Base

class RoleModule(Base):
    __tablename__ = "role_module"
    __table_args__ = {'schema': 'docucr'}
    
    id = Column(String, primary_key=True, index=True)
    role_id = Column(String, ForeignKey('docucr.role.id'), nullable=False)
    module_id = Column(String, ForeignKey('docucr.module.id'), nullable=False)
    privilege_id = Column(String, ForeignKey('docucr.privilege.id'), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
