from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from app.models.template import Template
from app.models.document_type import DocumentType
from fastapi import HTTPException, status

class TemplateService:
    def __init__(self, db: Session):
        self.db = db

    def get_all(self) -> List[Dict]:
        """Get all templates with document type info"""
        templates = self.db.query(Template).join(DocumentType).all()
        return [{
            "id": str(t.id),
            "template_name": t.template_name,
            "description": t.description,
            "document_type_id": str(t.document_type_id),
            "status_id": t.status_id,
            "extraction_fields": t.extraction_fields,
            "created_at": t.created_at.isoformat(),
            "updated_at": t.updated_at.isoformat()
        } for t in templates]

    def get_by_id(self, template_id: str) -> Dict:
        """Get template by ID"""
        template = self.db.query(Template).filter(Template.id == template_id).first()
        if not template:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Template not found"
            )
        return {
            "id": str(template.id),
            "template_name": template.template_name,
            "description": template.description,
            "document_type_id": str(template.document_type_id),
            "status_id": template.status_id,
            "extraction_fields": template.extraction_fields,
            "created_at": template.created_at.isoformat(),
            "updated_at": template.updated_at.isoformat()
        }

    def get_by_document_type(self, document_type_id: str) -> List[Dict]:
        """Get all templates for a specific document type"""
        templates = self.db.query(Template).filter(Template.document_type_id == document_type_id).all()
        return [{
            "id": str(t.id),
            "template_name": t.template_name,
            "description": t.description,
            "document_type_id": str(t.document_type_id),
            "status_id": t.status_id,
            "extraction_fields": t.extraction_fields,
            "created_at": t.created_at.isoformat(),
            "updated_at": t.updated_at.isoformat()
        } for t in templates]

    def create(self, template_name: str, document_type_id: str, description: Optional[str] = None, 
               extraction_fields: Optional[List[Dict[str, Any]]] = None, status_id: str = 'active') -> Dict:
        """Create a new template"""
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
        return {
            "id": str(template.id),
            "template_name": template.template_name,
            "description": template.description,
            "document_type_id": str(template.document_type_id),
            "status_id": template.status_id,
            "extraction_fields": template.extraction_fields,
            "created_at": template.created_at.isoformat(),
            "updated_at": template.updated_at.isoformat()
        }

    def update(self, template_id: str, template_name: Optional[str] = None, 
               description: Optional[str] = None, document_type_id: Optional[str] = None,
               extraction_fields: Optional[List[Dict[str, Any]]] = None, status_id: Optional[str] = None) -> Dict:
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
        return {
            "id": str(template.id),
            "template_name": template.template_name,
            "description": template.description,
            "document_type_id": str(template.document_type_id),
            "status_id": template.status_id,
            "extraction_fields": template.extraction_fields,
            "created_at": template.created_at.isoformat(),
            "updated_at": template.updated_at.isoformat()
        }

    def activate(self, template_id: str) -> Dict:
        """Activate a template"""
        return self.update(template_id, status_id='active')

    def deactivate(self, template_id: str) -> Dict:
        """Deactivate a template"""
        return self.update(template_id, status_id='inactive')