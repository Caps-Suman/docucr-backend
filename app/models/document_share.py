from sqlalchemy import (
    Column,
    String,
    DateTime,
    ForeignKey,
    Integer,
    UniqueConstraint,
    Index
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .module import Base
import uuid


class DocumentShare(Base):
    __tablename__ = "document_shares"
    __table_args__ = (
        # Prevent duplicate shares
        UniqueConstraint(
            "document_id",
            "user_id",
            name="uq_document_user_share"
        ),

        # Performance indexes
        Index("ix_document_shares_user_id", "user_id"),
        Index("ix_document_shares_document_id", "document_id"),

        {"schema": "docucr"}
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    document_id = Column(
        Integer,
        ForeignKey("docucr.documents.id", ondelete="CASCADE"),
        nullable=False
    )

    user_id = Column(
        String,
        ForeignKey("docucr.user.id", ondelete="CASCADE"),
        nullable=False
    )

    shared_by = Column(
        String,
        ForeignKey("docucr.user.id", ondelete="SET NULL"),
        nullable=True
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )

    # Relationships
    document = relationship(
        "Document",
        back_populates="shares"
    )

    user = relationship(
        "User",
        foreign_keys=[user_id],
        back_populates="shared_documents"
    )

    shared_by_user = relationship(
        "User",
        foreign_keys=[shared_by]
    )
