from sqlalchemy import Column, String, Text, DateTime, ForeignKey, Integer, Boolean, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .module import Base

class Form(Base):
    __tablename__ = "form"
    __table_args__ = {'schema': 'docucr'}
    
    id = Column(String, primary_key=True, index=True)
    name = Column(String(100), nullable=False, index=True)
    description = Column(Text, nullable=True)
    status_id = Column(Integer, ForeignKey('docucr.status.id'), nullable=True)
    created_by = Column(String, ForeignKey('docucr.user.id'), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    status_relation = relationship("Status")

class FormField(Base):
    __tablename__ = "form_field"
    __table_args__ = {'schema': 'docucr'}
    
    id = Column(String, primary_key=True, index=True)
    form_id = Column(String, ForeignKey('docucr.form.id', ondelete='CASCADE'), nullable=False)
    field_type = Column(String(50), nullable=False)  # text, textarea, number, email, select, checkbox, radio, date
    label = Column(String(200), nullable=False)
    placeholder = Column(String(200), nullable=True)
    required = Column(Boolean, default=False)
    default_value = Column(JSON, nullable=True)
    options = Column(JSON, nullable=True)  # For select, checkbox, radio
    validation = Column(JSON, nullable=True)  # Validation rules
    order = Column(Integer, nullable=False)
    is_system = Column(Boolean, default=False)  # System field flag
    created_at = Column(DateTime(timezone=True), server_default=func.now())
