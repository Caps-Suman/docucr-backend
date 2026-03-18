from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from typing import List, Optional
from fastapi import HTTPException

from app.models.document_type import DocumentType
from app.models.status import Status


class DocumentTypeService:
    def __init__(self, db: Session, current_user):
        self.db = db
        self.current_user = current_user

    # --------------------------------------------------
    # ORG CONTEXT
    # --------------------------------------------------
    def _get_org_id(self):
        if not self.current_user:
            return None
        return getattr(self.current_user, "context_organisation_id", None) or getattr(self.current_user, "organisation_id", None)

    # --------------------------------------------------
    # DUPLICATE CHECK
    # --------------------------------------------------
    def _check_duplicate(self, name: str, exclude_id: Optional[str] = None) -> bool:
        org_id = self._get_org_id()
        if not org_id:
            raise HTTPException(403, "No organisation selected")

        query = self.db.query(DocumentType).filter(
            DocumentType.organisation_id == org_id,
            DocumentType.name.ilike(name)
        )

        if exclude_id:
            query = query.filter(DocumentType.id != exclude_id)

        return self.db.query(query.exists()).scalar()

    # --------------------------------------------------
    # GET ALL
    # --------------------------------------------------
    def get_all(self) -> List[DocumentType]:
        org_id = self._get_org_id()
        if not org_id:
            raise HTTPException(403, "No organisation selected")

        return (
            self.db.query(DocumentType)
            .filter(DocumentType.organisation_id == org_id)
            .order_by(DocumentType.name)
            .all()
        )

    # --------------------------------------------------
    # GET ACTIVE
    # --------------------------------------------------
    def get_active(self) -> List[DocumentType]:
        org_id = self._get_org_id()
        if not org_id:
            raise HTTPException(403, "No organisation selected")

        active_status = self.db.query(Status).filter(Status.code == "ACTIVE").first()

        query = self.db.query(DocumentType).filter(
            DocumentType.organisation_id == org_id
        )

        if active_status:
            query = query.filter(DocumentType.status_id == active_status.id)

        return query.order_by(DocumentType.name).all()

    # --------------------------------------------------
    # GET BY ID
    # --------------------------------------------------
    def get_by_id(self, document_type_id: str) -> DocumentType:
        org_id = self._get_org_id()
        if not org_id:
            raise HTTPException(403, "No organisation selected")

        doc = (
            self.db.query(DocumentType)
            .filter(
                DocumentType.id == document_type_id,
                DocumentType.organisation_id == org_id
            )
            .first()
        )

        if not doc:
            raise HTTPException(404, "Document type not found")

        return doc

    # --------------------------------------------------
    # CREATE
    # --------------------------------------------------
    def create(self, name: str, description: Optional[str] = None, status_id: Optional[str] = None):
        org_id = self._get_org_id()
        if not org_id:
            raise HTTPException(403, "No organisation selected")

        name = name.strip().upper()

        if self._check_duplicate(name):
            raise HTTPException(400, f"Document type '{name}' already exists")

        # -----------------------------
        # Resolve status → DEFAULT ACTIVE
        # -----------------------------
        if status_id:
            if isinstance(status_id, str) and not status_id.isdigit():
                st = self.db.query(Status).filter(Status.code == status_id).first()
                status_id_val = st.id if st else status_id
            else:
                status_id_val = status_id
        else:
            active = self.db.query(Status).filter(Status.code == "ACTIVE").first()
            if not active:
                raise HTTPException(400, "Active status missing")
            status_id_val = active.id

        doc = DocumentType(
            name=name,
            description=description,
            status_id=status_id_val,
            organisation_id=org_id
        )

        self.db.add(doc)
        self.db.commit()
        self.db.refresh(doc)
        return doc

    # --------------------------------------------------
    # UPDATE
    # --------------------------------------------------
    def update(self, document_type_id: str, name: Optional[str] = None,
               description: Optional[str] = None, status_id: Optional[str] = None):

        doc = self.get_by_id(document_type_id)

        if name is not None:
            name = name.strip().upper()

            if self._check_duplicate(name, exclude_id=document_type_id):
                raise HTTPException(400, f"Document type '{name}' already exists")

            doc.name = name

        if description is not None:
            doc.description = description

        if status_id is not None:
            if isinstance(status_id, str) and not status_id.isdigit():
                status_obj = self.db.query(Status).filter(
                    Status.code == status_id.upper()
                ).first()

                if not status_obj:
                    raise HTTPException(400, f"Status '{status_id}' not found")

                status_id = status_obj.id

            doc.status_id = status_id

        try:
            self.db.commit()
            self.db.refresh(doc)
            return doc
        except IntegrityError:
            self.db.rollback()
            raise HTTPException(400, "Document type update failed")
        
    def activate(self, document_type_id: str) -> DocumentType:
        active_status = self.db.query(Status).filter(Status.code == 'ACTIVE').first()
        if not active_status:
             raise HTTPException(status_code=400, detail="Active status not found")
        return self.update(document_type_id, status_id=active_status.id)

    def deactivate(self, document_type_id: str) -> DocumentType:
        inactive_status = self.db.query(Status).filter(Status.code == 'INACTIVE').first()
        if not inactive_status:
             raise HTTPException(status_code=400, detail="Inactive status not found")
        return self.update(document_type_id, status_id=inactive_status.id)

    def delete(self, document_type_id: str) -> str:
        document_type = self.get_by_id(document_type_id) # Using get_by_id for security check
        name = document_type.name
        self.db.delete(document_type)
        self.db.commit()
        return name