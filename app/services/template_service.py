from sqlalchemy.orm import Session, joinedload
from typing import List, Optional, Dict, Any
from app.models.template import Template
from app.models.document_type import DocumentType
from app.models.status import Status
from app.models.user import User
from fastapi import HTTPException, status

class TemplateService:
    def __init__(self, db: Session, current_user: Optional[User] = None):
        self.db = db
        self.current_user = current_user

    def _get_user_role_names(self) -> List[str]:
        if not self.current_user:
            return []
        if not hasattr(self.current_user, 'roles'):
            return []
        return [r.name for r in self.current_user.roles]

    def _get_context_org_id(self) -> Optional[str]:
        if not self.current_user:
            return None

        # block temp superadmin
        if getattr(self.current_user, "context_temp", False):
            return None

        return getattr(self.current_user, "context_organisation_id", None) or getattr(self.current_user, "organisation_id", None)

    def get_all(self) -> List[Dict]:

        if not self.current_user:
            raise HTTPException(status_code=401, detail="Authentication required")

        org_id = self._get_context_org_id()
        if not org_id:
            return []

        query = self.db.query(Template).options(
            joinedload(Template.document_type),
            joinedload(Template.status)
        ).filter(
            Template.organisation_id == org_id
        )

        templates = query.all()

        result = []
        for template in templates:
            result.append({
                "id": template.id,
                "template_name": template.template_name,
                "description": template.description,
                "document_type_id": template.document_type_id,
                "status_id": template.status_id,
                "statusCode": template.status.code if template.status else "",
                "extraction_fields": template.extraction_fields,
                "created_at": template.created_at,
                "updated_at": template.updated_at,
                "document_type": {
                    "id": template.document_type.id,
                    "name": template.document_type.name,
                    "description": template.document_type.description
                } if template.document_type else None
            })

        return result

    def get_by_id(self, template_id: str) -> Template:

        if not self.current_user:
            raise HTTPException(status_code=401, detail="Authentication required")

        org_id = self._get_context_org_id()
        if not org_id:
            raise HTTPException(status_code=403, detail="Access denied")

        template = self.db.query(Template).options(
            joinedload(Template.document_type),
            joinedload(Template.status)
        ).filter(
            Template.id == template_id,
            Template.organisation_id == org_id
        ).first()

        if not template:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Template not found"
            )

        return template

    def get_by_document_type(self, document_type_id: str) -> List[Template]:

        if not self.current_user:
            return []

        org_id = self._get_context_org_id()
        if not org_id:
            return []

        return self.db.query(Template).filter(
            Template.document_type_id == document_type_id,
            Template.organisation_id == org_id
        ).all()
    
    def create(
    self,
    template_name: str,
    document_type_id: str,
    description: Optional[str] = None,
    extraction_fields: Optional[List[Dict[str, Any]]] = None,
    status_id: Optional[str] = None,
    user_id: Optional[str] = None
) -> Template:

        if not self.current_user:
            raise HTTPException(401, "Authentication required")

        org_id = getattr(self.current_user, "context_organisation_id", None) or getattr(self.current_user, "organisation_id", None)
        is_super = getattr(self.current_user, "context_is_superadmin", getattr(self.current_user, "is_superuser", False))

        if not is_super and not org_id:
            raise HTTPException(403, "No organisation selected")

        # -----------------------------
        # Resolve ACTIVE + INACTIVE status ids
        # -----------------------------
        active_status = self.db.query(Status).filter(Status.code == "ACTIVE").first()
        inactive_status = self.db.query(Status).filter(Status.code == "INACTIVE").first()

        if not active_status:
            raise HTTPException(400, "Active status missing")
        if not inactive_status:
            raise HTTPException(400, "Inactive status missing")

        # -----------------------------
        # Resolve requested status
        # DEFAULT → ACTIVE
        # -----------------------------
        if status_id:
            if isinstance(status_id, str) and not status_id.isdigit():
                st = self.db.query(Status).filter(Status.code == status_id).first()
                status_id_val = st.id if st else status_id
            else:
                status_id_val = status_id
        else:
            status_id_val = active_status.id

        # -----------------------------
        # Validate doc type
        # -----------------------------
        doc_type = self.db.query(DocumentType).filter(
            DocumentType.id == document_type_id
        ).first()

        if not doc_type:
            raise HTTPException(400, "Document type not found")

        # -----------------------------
        # If creating ACTIVE → deactivate old one
        # -----------------------------
        if status_id_val == active_status.id:
            existing_active = self.db.query(Template).filter(
                Template.document_type_id == document_type_id,
                Template.organisation_id == org_id,
                Template.status_id == active_status.id
            ).first()

            if existing_active:
                existing_active.status_id = inactive_status.id

        # -----------------------------
        # Create template
        # -----------------------------
        template = Template(
            template_name=template_name,
            description=description,
            document_type_id=document_type_id,
            status_id=status_id_val,
            extraction_fields=extraction_fields or [],
            created_by=self.current_user.id,
            organisation_id=org_id
        )

        self.db.add(template)
        self.db.commit()
        self.db.refresh(template)
        return template

    def update(
    self,
    template_id: str,
    template_name: Optional[str] = None,
    description: Optional[str] = None,
    document_type_id: Optional[str] = None,
    extraction_fields: Optional[List[Dict[str, Any]]] = None,
    status_id: Optional[str] = None,
) -> Template:

        template = self.get_by_id(template_id)

        # -----------------------------
        # Resolve new status
        # -----------------------------
        new_status_id = template.status_id

        if status_id is not None:
            if isinstance(status_id, str) and not status_id.isdigit():
                st = self.db.query(Status).filter(Status.code == status_id).first()
                if st:
                    new_status_id = st.id
            else:
                new_status_id = status_id

        # -----------------------------
        # Resolve new document type
        # -----------------------------
        new_doc_type = document_type_id or template.document_type_id

        # -----------------------------
        # CONFLICT CHECK
        # ONLY IF ACTIVATING
        # -----------------------------
        active_status = (
            self.db.query(Status).filter(Status.code == "ACTIVE").first()
        )

        if active_status and new_status_id == active_status.id:

            conflict = self.db.query(Template).filter(
                Template.document_type_id == new_doc_type,
                Template.status_id == active_status.id,
                Template.organisation_id == template.organisation_id,
                Template.id != template.id,
            ).first()

            if conflict:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Active template already exists for this document type",
                )

        # -----------------------------
        # Validate document type
        # -----------------------------
        if document_type_id:
            document_type = (
                self.db.query(DocumentType)
                .filter(DocumentType.id == document_type_id)
                .first()
            )
            if not document_type:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Document type not found",
                )

        # -----------------------------
        # Apply updates
        # -----------------------------
        if template_name is not None:
            template.template_name = template_name

        if description is not None:
            template.description = description

        if document_type_id is not None:
            template.document_type_id = document_type_id

        template.status_id = new_status_id

        if extraction_fields is not None:
            template.extraction_fields = extraction_fields

        self.db.commit()
        self.db.refresh(template)

        return template


    def _update_status(self, template_id: str, status_code: str) -> Template:
        """Helper method to update template status"""
        status_obj = self.db.query(Status).filter(Status.code == status_code).first()
        if not status_obj:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"{status_code} status not found in status table"
            )
        return self.update(template_id, status_id=str(status_obj.id))

    def activate(self, template_id: str) -> Template:
        """Activate a template"""
        return self._update_status(template_id, 'ACTIVE')

    def deactivate(self, template_id: str) -> Template:
        """Deactivate a template"""
        return self._update_status(template_id, 'INACTIVE')

    def delete(self, template_id: str) -> Optional[str]:
        """Delete a template"""
        # get_by_id checks permissions
        template = self.get_by_id(template_id)
        
        name = template.template_name
        self.db.delete(template)
        self.db.commit()
        return name