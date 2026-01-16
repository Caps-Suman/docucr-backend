from sqlalchemy import Column, String, ForeignKey, DateTime
from sqlalchemy.sql import func
from .module import Base

class UserRoleModule(Base):
    __tablename__ = "user_role_module"
    __table_args__ = {'schema': 'docucr'}
    
    id = Column(String, primary_key=True, index=True)
    user_id = Column(String, ForeignKey('docucr.user.id'), nullable=False)
    role_module_id = Column(String, ForeignKey('docucr.role_module.id'), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
