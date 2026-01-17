from sqlalchemy.orm import Session, joinedload
from typing import List, Optional, Dict, Any
from app.models.template import Template
from app.models.document_type import DocumentType
from app.models.status import Status
from fastapi import HTTPException, status

class TemplateService:
    def __init__(self, db: Session):
        self.db = db

    def get_all(self) -> List[Template]:
        """Get all templates with document type info"""
        return self.db.query(Template).options(joinedload(Template.document_type)).all()

    def get_by_id(self, template_id: str) -> Template:
        """Get template by ID"""
        template = self.db.query(Template).options(joinedload(Template.document_type)).filter(Template.id == template_id).first()
        if not template:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Template not found"
            )
        return template

    def get_by_document_type(self, document_type_id: str) -> List[Template]:
        """Get all templates for a specific document type"""
        return self.db.query(Template).filter(Template.document_type_id == document_type_id).all()

    def create(self, template_name: str, document_type_id: str, description: Optional[str] = None, 
               extraction_fields: Optional[List[Dict[str, Any]]] = None, status_id: Optional[str] = None) -> Template:
        """Create a new template"""
        # Get inactive status if not provided
        if status_id is None:
            inactive_status = self.db.query(Status).filter(Status.name == 'INACTIVE').first()
            if not inactive_status:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Inactive status not found in status table"
                )
            status_id = inactive_status.id
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
            status_id=status_id,
            extraction_fields=extraction_fields or []
        )
        
        self.db.add(template)
        self.db.commit()
        self.db.refresh(template)
        return template

    def update(self, template_id: str, template_name: Optional[str] = None, 
               description: Optional[str] = None, document_type_id: Optional[str] = None,
               extraction_fields: Optional[List[Dict[str, Any]]] = None, status_id: Optional[str] = None) -> Template:
        """Update a template"""
        template = self.db.query(Template).filter(Template.id == template_id).first()
        if not template:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Template not found"
            )
        
        # Verify document type exists if being updated
        if document_type_id:
            document_type = self.db.query(DocumentType).filter(DocumentType.id == document_type_id).first()
            if not document_type:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Document type not found"
                )
        
        # Update fields
        if template_name is not None:
            template.template_name = template_name
        if description is not None:
            template.description = description
        if document_type_id is not None:
            template.document_type_id = document_type_id
        if status_id is not None:
            template.status_id = status_id
        if extraction_fields is not None:
            template.extraction_fields = extraction_fields
        
        self.db.commit()
        self.db.refresh(template)
        return template

    def _update_status(self, template_id: str, status_name: str) -> Template:
        """Helper method to update template status"""
        status = self.db.query(Status).filter(Status.name == status_name).first()
        if not status:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"{status_name} status not found in status table"
            )
        return self.update(template_id, status_id=status.id)

    def activate(self, template_id: str) -> Template:
        """Activate a template"""
        return self._update_status(template_id, 'ACTIVE')

    def deactivate(self, template_id: str) -> Template:
        """Deactivate a template"""
        return self._update_status(template_id, 'INACTIVE')