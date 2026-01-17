from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Dict, Any
from pydantic import BaseModel, field_serializer
from datetime import datetime
from uuid import UUID
from app.core.database import get_db
from app.services.template_service import TemplateService

router = APIRouter(prefix="/api/templates", tags=["templates"])

# Pydantic models
class TemplateCreate(BaseModel):
    template_name: str
    description: str = None
    document_type_id: str
    extraction_fields: List[Dict[str, Any]] = []

class TemplateUpdate(BaseModel):
    template_name: str = None
    description: str = None
    document_type_id: str = None
    extraction_fields: List[Dict[str, Any]] = None

class DocumentTypeInfo(BaseModel):
    id: UUID
    name: str
    description: str = None
    
    @field_serializer('id')
    def serialize_id(self, value: UUID) -> str:
        return str(value)

class TemplateResponse(BaseModel):
    id: UUID
    template_name: str
    description: str = None
    document_type_id: UUID
    extraction_fields: List[Dict[str, Any]]
    created_at: datetime
    updated_at: datetime
    document_type: DocumentTypeInfo = None

    @field_serializer('id', 'document_type_id')
    def serialize_uuid(self, value: UUID) -> str:
        return str(value)
    
    @field_serializer('created_at', 'updated_at')
    def serialize_datetime(self, value: datetime) -> str:
        return value.isoformat()

    class Config:
        from_attributes = True

@router.get("/", response_model=List[TemplateResponse])
async def get_templates(
    db: Session = Depends(get_db)
):
    """Get all templates with document type info"""
    service = TemplateService(db)
    return service.get_all()

@router.post("/", response_model=TemplateResponse, status_code=status.HTTP_201_CREATED)
async def create_template(
    template_data: TemplateCreate,
    db: Session = Depends(get_db)
):
    """Create a new template"""
    service = TemplateService(db)
    return service.create(
        template_data.template_name,
        template_data.document_type_id,
        template_data.description,
        template_data.extraction_fields
    )

@router.get("/{template_id}", response_model=TemplateResponse)
async def get_template(
    template_id: str,
    db: Session = Depends(get_db)
):
    """Get a specific template"""
    service = TemplateService(db)
    return service.get_by_id(template_id)

@router.put("/{template_id}", response_model=TemplateResponse)
async def update_template(
    template_id: str,
    template_data: TemplateUpdate,
    db: Session = Depends(get_db)
):
    """Update a template"""
    service = TemplateService(db)
    return service.update(
        template_id,
        template_data.template_name,
        template_data.description,
        template_data.document_type_id,
        template_data.extraction_fields
    )

@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_template(
    template_id: str,
    db: Session = Depends(get_db)
):
    """Delete a template"""
    service = TemplateService(db)
    service.delete(template_id)

@router.get("/by-document-type/{document_type_id}", response_model=List[TemplateResponse])
async def get_templates_by_document_type(
    document_type_id: str,
    db: Session = Depends(get_db)
):
    """Get all templates for a specific document type"""
    service = TemplateService(db)
    return service.get_by_document_type(document_type_id)