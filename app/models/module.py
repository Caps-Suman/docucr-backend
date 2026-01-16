from sqlalchemy import Column, String, Boolean, Text, Integer, JSON, DateTime
from sqlalchemy.sql import func
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class Module(Base):
    __tablename__ = "module"
    __table_args__ = {'schema': 'docucr'}
    
    id = Column(String, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False, index=True)
    label = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    route = Column(String, nullable=False)
    icon = Column(String, nullable=True)
    category = Column(String, nullable=False)
    has_submodules = Column(Boolean, default=False)
    submodules = Column(JSON, default=list)
    is_active = Column(Boolean, default=True)
    display_order = Column(Integer, default=0)
    color_from = Column(String, nullable=True)
    color_to = Column(String, nullable=True)
    color_shadow = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
