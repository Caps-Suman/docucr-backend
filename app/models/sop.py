from sqlalchemy import Column, String, DateTime, ForeignKey, Integer
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from .module import Base
import uuid


class SOP(Base):
    __tablename__ = "sop"
    __table_args__ = {"schema": "docucr"}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)

    title = Column(String, nullable=False)
    category = Column(String, nullable=False)
    provider_type = Column(String, nullable=False)  # new | existing

    client_id = Column(UUID(as_uuid=True), ForeignKey("docucr.client.id"), nullable=True)

    provider_info = Column(JSONB, nullable=True)
    workflow_process = Column(JSONB, nullable=True)
    billing_guidelines = Column(JSONB, nullable=True)
    payer_guidelines=Column(JSONB, nullable=True)
    coding_rules = Column(JSONB, nullable=True)
    coding_rules_cpt = Column(JSONB, nullable=True, default=list)
    coding_rules_icd = Column(JSONB, nullable=True, default=list)

    # 🔒 Lifecycle status (ONLY ACTIVE / INACTIVE)
    status_id = Column(Integer, ForeignKey("docucr.status.id"), nullable=True)

    # 🔁 Workflow / processing status
    workflow_status_id = Column(Integer, ForeignKey("docucr.status.id"), nullable=True)

    created_by = Column(String, ForeignKey("docucr.user.id"), nullable=True)
    organisation_id = Column(String, ForeignKey("docucr.organisation.id"), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # ---------- Relationships ----------
    client = relationship("Client", backref="sops")
    creator = relationship("User", foreign_keys=[created_by], backref="created_sops")
    organisation = relationship("Organisation", foreign_keys=[organisation_id], backref="sops")

    lifecycle_status = relationship(
        "Status",
        foreign_keys=[status_id],
        lazy="joined"
    )

    workflow_status = relationship(
        "Status",
        foreign_keys=[workflow_status_id],
        lazy="joined"
    )
