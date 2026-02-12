from fastapi import APIRouter, Depends, HTTPException, status, Request, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import List
from pydantic import BaseModel
from app.core.database import get_db
from app.core.security import get_current_user
from app.core.permissions import Permission
from app.models.document_type import DocumentType
from app.models.status import Status
from app.services.document_type_service import DocumentTypeService
from app.services.activity_service import ActivityService
from app.models.user import User
from fastapi import Request
from uuid import UUID
from datetime import datetime
from typing import Optional
router = APIRouter(prefix="/api/document-types", tags=["document-types"], dependencies=[Depends(get_current_user)])

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
    id: UUID
    name: str
    description: Optional[str]
    status_id: int
    statusCode: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

@router.get("", response_model=List[DocumentTypeResponse])
def get_document_types(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all document types"""
    service = DocumentTypeService(db, current_user)
    return service.get_all()

@router.get("/dropdown", response_model=List[dict])
def get_document_type_dropdown(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Lightweight API for dropdowns
    - ACTIVE only
    - id + name only
    """
    # Logic moved to service, reusing get_active but formatting response
    service = DocumentTypeService(db, current_user)
    active_types = service.get_active()

    return [
        {"id": str(dt.id), "name": dt.name}
        for dt in sorted(active_types, key=lambda x: x.name)
    ]

@router.get("/active", response_model=List[DocumentTypeResponse])
def get_active_document_types(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all active document types"""
    service = DocumentTypeService(db, current_user)
    return service.get_active()

@router.post("", response_model=DocumentTypeResponse, status_code=status.HTTP_201_CREATED)
def create_document_type(
    document_type_data: DocumentTypeCreate,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    permission: bool = Depends(Permission("document_types", "CREATE")),
    current_user: User = Depends(get_current_user)
):
    """Create a new document type"""
    service = DocumentTypeService(db, current_user)
    result = service.create(document_type_data.name, document_type_data.description, document_type_data.status_id)
    
    ActivityService.log(
        db=db,
        action="CREATE",
        entity_type="document_type",
        entity_id=result.id,
        user_id=current_user.id,
        details={"name": result.name},
        request=request,
        background_tasks=background_tasks
    )
    
    return result

@router.get("/{document_type_id}", response_model=DocumentTypeResponse)
def get_document_type(
    document_type_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get a specific document type"""
    service = DocumentTypeService(db, current_user)
    return service.get_by_id(document_type_id)

@router.put("/{document_type_id}", response_model=DocumentTypeResponse)
def update_document_type(
    document_type_id: str,
    document_type_data: DocumentTypeUpdate,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    permission: bool = Depends(Permission("document_types", "UPDATE")),
    current_user: User = Depends(get_current_user)
):
    """Update a document type"""
    service = DocumentTypeService(db, current_user)
    
    # Calculate changes BEFORE update
    # Fetching through service to ensure access control if needed, or directly from DB if service fetch is restricted
    # Using service.get_by_id is safer as it includes org checks
    original_obj = service.get_by_id(document_type_id)

    changes = ActivityService.calculate_changes(
        original_obj, 
        {"name": document_type_data.name, "description": document_type_data.description, "status_id": document_type_data.status_id}
    )

    result = service.update(document_type_id, document_type_data.name, document_type_data.description, document_type_data.status_id)

    ActivityService.log(
        db=db,
        action="UPDATE",
        entity_type="document_type",
        entity_id=document_type_id,
        user_id=current_user.id,
        details={"name": result.name, "changes": changes},
        request=request,
        background_tasks=background_tasks
    )
    
    return result

@router.patch("/{document_type_id}/activate", response_model=DocumentTypeResponse)
def activate_document_type(
    document_type_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    permission: bool = Depends(Permission("document_types", "UPDATE")),
    current_user: User = Depends(get_current_user)
):
    """Activate a document type"""
    service = DocumentTypeService(db, current_user)
    result = service.activate(document_type_id)
    
    ActivityService.log(
        db=db,
        action="ACTIVATE",
        entity_type="document_type",
        entity_id=document_type_id,
        user_id=current_user.id,
        request=request,
        background_tasks=background_tasks
    )
    
    return result

@router.patch("/{document_type_id}/deactivate", response_model=DocumentTypeResponse)
def deactivate_document_type(
    document_type_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    permission: bool = Depends(Permission("document_types", "UPDATE")),
    current_user: User = Depends(get_current_user)
):
    """Deactivate a document type"""
    service = DocumentTypeService(db, current_user)
    result = service.deactivate(document_type_id)
    
    ActivityService.log(
        db=db,
        action="DEACTIVATE",
        entity_type="document_type",
        entity_id=document_type_id,
        user_id=current_user.id,
        request=request,
        background_tasks=background_tasks
    )
    
    return result

@router.delete("/{document_type_id}")
def delete_document_type(
    document_type_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    permission: bool = Depends(Permission("document_types", "DELETE")),
    current_user: User = Depends(get_current_user)
):
    """Delete a document type"""
    service = DocumentTypeService(db, current_user)
    name = service.delete(document_type_id)
    
    ActivityService.log(
        db=db,
        action="DELETE",
        entity_type="document_type",
        entity_id=document_type_id,
        user_id=current_user.id,
        details={"name": name},
        request=request,
        background_tasks=background_tasks
    )

    return {"message": "Document type deleted successfully"}