from sqlalchemy import Column, String, Text, DateTime, UniqueConstraint, func, ForeignKey, JSON, Integer, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from .module import Base
import uuid

class Template(Base):
    __tablename__ = "templates"
    __table_args__ = (
        UniqueConstraint("template_name", "document_type_id"),
        {"schema": "docucr"}
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    template_name = Column(String(100), nullable=False)
    description = Column(Text)

    document_type_id = Column(
        UUID(as_uuid=True),
        ForeignKey("docucr.document_types.id"),
        nullable=False
    )

    status_id = Column(
        Integer,
        ForeignKey("docucr.status.id"),
        nullable=False
    )

    extraction_fields = Column(
        JSON,
        nullable=False,
        server_default=text("'[]'::json")
    )
    created_by = Column(
        String,
        ForeignKey("docucr.user.id"),
        nullable=False
    )

    updated_by = Column(
        String,
        ForeignKey("docucr.user.id"),
        nullable=True
    )


    creator = relationship("User", foreign_keys=[created_by])
    updater = relationship("User", foreign_keys=[updated_by])
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    document_type = relationship("DocumentType", back_populates="templates")
    status = relationship("Status", back_populates="templates")

    def __repr__(self):
        return f"<Template {self.template_name}>"
