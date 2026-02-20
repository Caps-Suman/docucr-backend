from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Integer
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
from .module import Base

class Organisation(Base):
    __tablename__ = "organisation"
    __table_args__ = {'schema': 'docucr'}

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    status_id = Column(Integer, ForeignKey('docucr.status.id'))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    users = relationship("User", back_populates="organisation")

    status_relation = relationship("Status", back_populates="organisations")