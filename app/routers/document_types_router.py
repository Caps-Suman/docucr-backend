from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from pydantic import BaseModel
from app.core.database import get_db
from app.services.document_type_service import DocumentTypeService

router = APIRouter(prefix="/api/document-types", tags=["document-types"])

# Pydantic models
class DocumentTypeCreate(BaseModel):
    name: str
    description: str = None
    status_id: str = 'inactive'

class DocumentTypeUpdate(BaseModel):
    name: str = None
    description: str = None
    status_id: str = None

class DocumentTypeResponse(BaseModel):
    id: str
    name: str
    description: str = None
    status_id: str
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True

@router.get("/", response_model=List[DocumentTypeResponse])
async def get_document_types(
    db: Session = Depends(get_db)
):
    """Get all document types"""
    service = DocumentTypeService(db)
    return service.get_all()

@router.post("/", response_model=DocumentTypeResponse, status_code=status.HTTP_201_CREATED)
async def create_document_type(
    document_type_data: DocumentTypeCreate,
    db: Session = Depends(get_db)
):
    """Create a new document type"""
    service = DocumentTypeService(db)
    return service.create(document_type_data.name, document_type_data.description, document_type_data.status_id)

@router.get("/{document_type_id}", response_model=DocumentTypeResponse)
async def get_document_type(
    document_type_id: str,
    db: Session = Depends(get_db)
):
    """Get a specific document type"""
    service = DocumentTypeService(db)
    return service.get_by_id(document_type_id)

@router.put("/{document_type_id}", response_model=DocumentTypeResponse)
async def update_document_type(
    document_type_id: str,
    document_type_data: DocumentTypeUpdate,
    db: Session = Depends(get_db)
):
    """Update a document type"""
    service = DocumentTypeService(db)
    return service.update(document_type_id, document_type_data.name, document_type_data.description, document_type_data.status_id)

@router.patch("/{document_type_id}/activate", response_model=DocumentTypeResponse)
async def activate_document_type(
    document_type_id: str,
    db: Session = Depends(get_db)
):
    """Activate a document type"""
    service = DocumentTypeService(db)
    return service.activate(document_type_id)

@router.patch("/{document_type_id}/deactivate", response_model=DocumentTypeResponse)
async def deactivate_document_type(
    document_type_id: str,
    db: Session = Depends(get_db)
):
    """Deactivate a document type"""
    service = DocumentTypeService(db)
    return service.deactivate(document_type_id)