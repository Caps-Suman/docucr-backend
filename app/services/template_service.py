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

    def _get_organisation_id(self) -> Optional[str]:
        if not self.current_user:
            return None
        if getattr(self.current_user, 'is_org', False):
            return str(self.current_user.id)
        return getattr(self.current_user, 'organisation_id', None)

    def get_all(self) -> List[Dict]:
        """Get all templates with document type info based on role"""
        query = self.db.query(Template).options(
            joinedload(Template.document_type),
            joinedload(Template.status)
        )

        if self.current_user:
            role_names = self._get_user_role_names()
            
            if 'SUPER_ADMIN' in role_names or getattr(self.current_user, 'is_superuser', False):
                # Super Admin sees all
                pass
            elif any('ORGANISATION_ROLE' in r for r in role_names) or getattr(self.current_user, 'is_org', False):
                # Organisation Role sees only their own
                org_id = self._get_organisation_id()
                if org_id:
                    query = query.filter(Template.organisation_id == org_id)
                else:
                    return []
            else:
                 # Other roles see nothing
                return []

        templates = query.all()
        
        result = []
        for template in templates:
            template_dict = {
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
            }
            result.append(template_dict)
        
        return result

    def get_by_id(self, template_id: str) -> Template:
        """Get template by ID with role check"""
        query = self.db.query(Template).options(
            joinedload(Template.document_type),
            joinedload(Template.status)
        ).filter(Template.id == template_id)
        
        if self.current_user:
            role_names = self._get_user_role_names()
            is_super = 'SUPER_ADMIN' in role_names or getattr(self.current_user, 'is_superuser', False)
            is_org = any('ORGANISATION_ROLE' in r for r in role_names) or getattr(self.current_user, 'is_org', False)
            
            if is_org and not is_super:
                org_id = self._get_organisation_id()
                if org_id:
                    query = query.filter(Template.organisation_id == org_id)
                else:
                     raise HTTPException(status_code=403, detail="Access denied")
            elif not is_super and not is_org:
                 raise HTTPException(status_code=403, detail="Access denied")

        template = query.first()
        if not template:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Template not found"
            )
        return template

    def get_by_document_type(self, document_type_id: str) -> List[Template]:
        """Get all templates for a specific document type based on role"""
        query = self.db.query(Template).filter(Template.document_type_id == document_type_id)
        
        if self.current_user:
            role_names = self._get_user_role_names()
            
            if 'SUPER_ADMIN' in role_names or getattr(self.current_user, 'is_superuser', False):
                pass
            elif any('ORGANISATION_ROLE' in r for r in role_names) or getattr(self.current_user, 'is_org', False):
                org_id = self._get_organisation_id()
                if org_id:
                    query = query.filter(Template.organisation_id == org_id)
                else:
                    return []
            else:
                return []
                
        return query.all()

    def create(self, template_name: str, document_type_id: str, description: Optional[str] = None, 
               extraction_fields: Optional[List[Dict[str, Any]]] = None, status_id: Optional[str] = None,
               user_id: Optional[str] = None) -> Template:
        """Create a new template"""
        
        # Role check
        if not self.current_user:
            raise HTTPException(status_code=401, detail="Authentication required")

        existing_template = (
            self.db.query(Template)
            .filter(
                Template.document_type_id == document_type_id,
                Template.status_id == 8,
            )
            .first()
        )

        if existing_template:
            raise HTTPException(
                status_code=409,
                detail="Template already exists for this document type"
            )
        
        organisation_id = None
        created_by_id = None

        role_names = self._get_user_role_names()
        is_super = 'SUPER_ADMIN' in role_names or getattr(self.current_user, 'is_superuser', False)
        is_org = any('ORGANISATION_ROLE' in r for r in role_names) or getattr(self.current_user, 'is_org', False)
        
        if is_super:
            # 1. SUPER_ADMIN: Both column should be set null
            organisation_id = None
            created_by_id = None
        elif is_org:
            # 2. ORGANISATION_ROLE: created_by should be null and organisation_id should be set
            organisation_id = self._get_organisation_id()
            created_by_id = None
            if not organisation_id:
                 raise HTTPException(status_code=400, detail="Organisation ID missing for organisation user")
        else:
            # 3. Any other role: Both column should be set
            # First get organisation_id (Where belong this user)
            organisation_id = self._get_organisation_id()
            # Then set user_id into 'created_by' column
            created_by_id = self.current_user.id
            
            # Access logic: If normal user, do we allow create?
            # User request implied we should handle this case: "3. Any other role is logged in..."
            # Assuming allowed if they belong to an org.
            if not organisation_id:
                 # If user has no organisation, they probably shouldn't be creating templates unless they are super admin (handled above)
                 # But let's fail safe or deny? 
                 # PROMPT: "3. Any other role is logged in: Then both column should be set here"
                 # Implicitly allows it.
                 pass
            
            # Explicitly checking if we previously denied them.
            # "Any other role attempting to create a template must be denied" was the OLD rule.
            # The NEW error report says "Lets discuss for all role... 3. Any other role... Both column should be set".
            # This overrides the old rule.

        # Get inactive status if not provided (default)
        if status_id is None:
            inactive_status = self.db.query(Status).filter(Status.code == 'INACTIVE').first()
            if not inactive_status:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Inactive status not found in status table"
                )
            status_id_val = inactive_status.id
        else:
             if isinstance(status_id, str) and not status_id.isdigit():
                 st = self.db.query(Status).filter(Status.code == status_id).first()
                 if st:
                     status_id_val = st.id
                 else:
                     status_id_val = status_id
             else:
                 status_id_val = status_id

        # Verify document type exists
        document_type = self.db.query(DocumentType).filter(DocumentType.id == document_type_id).first()
        if not document_type:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Document type not found"
            )
        
        template = Template(
            template_name=template_name,
            description=description,
            document_type_id=document_type_id,
            status_id=8,
            extraction_fields=extraction_fields or [],
            created_by=created_by_id,
            organisation_id=organisation_id
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

            conflict = (
                self.db.query(Template)
                .filter(
                    Template.document_type_id == new_doc_type,
                    Template.status_id == active_status.id,
                    Template.id != template.id,
                )
                .first()
            )

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