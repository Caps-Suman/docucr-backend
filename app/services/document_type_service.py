from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from typing import List, Optional, Dict
from app.models.document_type import DocumentType
from app.models.status import Status
from app.models.user import User
from app.models.organisation import Organisation
from fastapi import HTTPException, status
from sqlalchemy import or_, func

class DocumentTypeService:
    def __init__(self, db: Session, current_user: Optional[User] = None):
        self.db = db
        self.current_user = current_user

    def _get_user_role_names(self) -> List[str]:
        if not self.current_user:
            return []
        # Handle case where roles might be missing or empty
        if not hasattr(self.current_user, 'roles'):
            return []
        return [r.name for r in self.current_user.roles]

    def _get_organisation_id(self) -> Optional[str]:
        if not self.current_user:
            return None
        
        # If user is an Organisation (flagged by security.py or check model)
        if getattr(self.current_user, 'is_org', False):
            return str(self.current_user.id)
            
        # If user is a User
        return getattr(self.current_user, 'organisation_id', None)

    def get_all(self) -> List[DocumentType]:
        """Get all document types based on role"""
        query = self.db.query(DocumentType).join(Status)
        
        if self.current_user:
            role_names = self._get_user_role_names()
            
            if 'SUPER_ADMIN' in role_names or getattr(self.current_user, 'is_superuser', False):
                # Super Admin sees all
                pass
            elif any('ORGANISATION_ROLE' in r for r in role_names) or getattr(self.current_user, 'is_org', False):
                # Organisation Role sees only their own
                org_id = self._get_organisation_id()
                if org_id:
                    query = query.filter(DocumentType.organisation_id == org_id)
                else:
                    return [] # Should not happen if logic is correct
            else:
                # Other roles see nothing
                return []
                
        return query.all()

    def get_active(self) -> List[DocumentType]:
        """Get all active document types based on role"""
        active_status = self.db.query(Status).filter(Status.code == 'ACTIVE').first()
        if not active_status:
            return self.get_all()
            
        query = self.db.query(DocumentType).join(Status).filter(DocumentType.status_id == active_status.id)
        
        if self.current_user:
            role_names = self._get_user_role_names()
            
            if 'SUPER_ADMIN' in role_names or getattr(self.current_user, 'is_superuser', False):
                pass  # no filter → all data

            # ALL OTHER USERS → fetch organisation-wise data
            else:
                org_id = self._get_organisation_id()
                if org_id:
                    query = query.filter(DocumentType.organisation_id == org_id)
                else:
                    return []
                
        return query.all()

    def get_by_id(self, document_type_id: str) -> DocumentType:
        """Get document type by ID with role check"""
        query = self.db.query(DocumentType).join(Status).filter(DocumentType.id == document_type_id)
        
        if self.current_user:
            role_names = self._get_user_role_names()
            is_super = 'SUPER_ADMIN' in role_names or getattr(self.current_user, 'is_superuser', False)
            is_org = any('ORGANISATION_ROLE' in r for r in role_names) or getattr(self.current_user, 'is_org', False)
            
            if is_org and not is_super:
                org_id = self._get_organisation_id()
                if org_id:
                    query = query.filter(DocumentType.organisation_id == org_id)
                else:
                     raise HTTPException(status_code=403, detail="Access denied")
            elif not is_super and not is_org:
                raise HTTPException(status_code=403, detail="Access denied")
                
        document_type = query.first()
        if not document_type:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document type not found"
            )
        return document_type

    @staticmethod
    def _check_duplicate(name: str, db: Session, current_user, exclude_id: Optional[str] = None) -> bool:
        query = db.query(DocumentType).filter(func.upper(DocumentType.name) == name.upper())

        if exclude_id:
            query = query.filter(DocumentType.id != exclude_id)

        # SaaS Scoping
        if getattr(current_user, "is_superuser", False):
            # Super Admin: Global scope (organisation_id is NULL)
            query = query.filter(DocumentType.organisation_id.is_(None))
        
        elif isinstance(current_user, Organisation):
            # Organisation object (from login)
            query = query.filter(DocumentType.organisation_id == str(current_user.id))
            
        elif isinstance(current_user, User):
            if current_user.organisation_id:
                # Organisation User
                query = query.filter(DocumentType.organisation_id == str(current_user.organisation_id))
            else:
                # Independent user -> Global scope
                query = query.filter(DocumentType.organisation_id.is_(None))
        else:
            # Fallback
            org_id = getattr(current_user, 'organisation_id', None)
            if org_id:
                query = query.filter(DocumentType.organisation_id == str(org_id))
            else:
                query = query.filter(DocumentType.organisation_id.is_(None))

        return query.first() is not None


    def create(self, name: str, description: Optional[str] = None, status_id: Optional[str] = None):
        # Role check
        if not self.current_user:
            raise HTTPException(status_code=401, detail="Authentication required")
            
        role_names = self._get_user_role_names()
        is_super = 'SUPER_ADMIN' in role_names or getattr(self.current_user, 'is_superuser', False)
        is_org = any('ORGANISATION_ROLE' in r for r in role_names) or getattr(self.current_user, 'is_org', False)
        
        organisation_id = None
        
        if is_super:
            organisation_id = None
        elif is_org:
            organisation_id = self._get_organisation_id()
            if not organisation_id:
                 raise HTTPException(status_code=400, detail="Organisation ID missing for organisation user")
        else:
            raise HTTPException(status_code=403, detail="Access denied")

        # Normalize
        name = name.strip().upper()

        # Duplicate check (SaaS-based)
        if self._check_duplicate(name, self.db, self.current_user):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Document type with name '{name}' already exists"
            )

        try:
            document_type = DocumentType(
                name=name,
                description=description,
                status_id=8,
                organisation_id=organisation_id
            )
            self.db.add(document_type)
            self.db.commit()
            self.db.refresh(document_type)
            return document_type

        except IntegrityError:
            self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Document type with this name already exists"
            )

    def update(self, document_type_id: str, name: Optional[str] = None,
           description: Optional[str] = None, status_id: Optional[str] = None):
           
        document_type = self.get_by_id(document_type_id) # Using get_by_id for security check

        if name is not None:
            name = name.strip().upper()
            
            # Duplicate check (SaaS-based) excluding current
            if self._check_duplicate(name, self.db, self.current_user, exclude_id=document_type_id):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Document type with name '{name}' already exists"
                )
            document_type.name = name

        if description is not None:
            document_type.description = description

        if status_id is not None:
            if isinstance(status_id, str) and not status_id.isdigit():
                status_obj = self.db.query(Status).filter(
                    Status.code == status_id.upper()
                ).first()
                if not status_obj:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Status '{status_id}' not found"
                    )
                status_id = status_obj.id
            document_type.status_id = status_id

        try:
            self.db.commit()
            self.db.refresh(document_type)
            return document_type

        except IntegrityError:
            self.db.rollback()
            raise HTTPException(
                status_code=400,
                detail="Document type with this name already exists"
            )

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