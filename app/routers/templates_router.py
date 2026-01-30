from fastapi import APIRouter, Depends, HTTPException, status, Request, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, field_serializer
from datetime import datetime
from uuid import UUID
from app.core.database import get_db
from app.core.security import get_current_user
from app.core.permissions import Permission
from app.services.template_service import TemplateService
from ..services.activity_service import ActivityService
from ..models.user import User

router = APIRouter(prefix="/api/templates", tags=["templates"], dependencies=[Depends(get_current_user)])

# Pydantic models
class TemplateCreate(BaseModel):
    template_name: str
    description: Optional[str] = None
    document_type_id: str
    status_id: Optional[str] = None
    extraction_fields: List[Dict[str, Any]] = []

class TemplateUpdate(BaseModel):
    template_name: Optional[str] = None
    description: Optional[str] = None
    document_type_id: Optional[str] = None
    status_id: Optional[str] = None
    extraction_fields: Optional[List[Dict[str, Any]]] = None

class DocumentTypeInfo(BaseModel):
    id: UUID
    name: str
    description: Optional[str] = None
    
    @field_serializer('id')
    def serialize_id(self, value: UUID) -> str:
        return str(value)

class TemplateResponse(BaseModel):
    id: UUID
    template_name: str
    description: Optional[str] = None
    document_type_id: UUID
    status_id: int
    statusCode: Optional[str] = None
    extraction_fields: List[Dict[str, Any]]
    created_at: datetime
    updated_at: datetime
    document_type: Optional[DocumentTypeInfo] = None

    @field_serializer('id', 'document_type_id')
    def serialize_uuid(self, value: UUID) -> str:
        return str(value)
    
    @field_serializer('created_at', 'updated_at')
    def serialize_datetime(self, value: datetime) -> str:
        return value.isoformat()

    @field_serializer('statusCode', when_used='always')
    def serialize_status_code(self, status_code: Optional[str]):
        return status_code or ""

    class Config:
        from_attributes = True


@router.get("/by-document-type/{document_type_id}", response_model=List[TemplateResponse])
def get_templates_by_document_type(
    document_type_id: str,
    db: Session = Depends(get_db)
):
    """Get all templates for a specific document type"""
    service = TemplateService(db)
    return service.get_by_document_type(document_type_id)

@router.get("/", response_model=List[TemplateResponse])
def get_templates(
    db: Session = Depends(get_db)
):
    """Get all templates with document type info"""
    service = TemplateService(db)
    return service.get_all()

@router.post("/", response_model=TemplateResponse, status_code=status.HTTP_201_CREATED)
def create_template(
    template_data: TemplateCreate,
    req: Request,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    permission: bool = Depends(Permission("templates_list", "CREATE"))
):
    """Create a new template"""
    service = TemplateService(db)
    template = service.create(
        template_data.template_name,
        template_data.document_type_id,
        template_data.description,
        template_data.extraction_fields,
        template_data.status_id,
        user_id=current_user.id
    )
    
    ActivityService.log(
        db,
        action="CREATE",
        entity_type="template",
        entity_id=str(template.id),
        user_id=current_user.id,
        details={"name": template.template_name},
        request=req,
        background_tasks=background_tasks
    )
    
    return template

@router.get("/{template_id}", response_model=TemplateResponse)
def get_template(
    template_id: str,
    db: Session = Depends(get_db)
):
    """Get a specific template"""
    service = TemplateService(db)
    return service.get_by_id(template_id)

@router.put("/{template_id}", response_model=TemplateResponse)
def update_template(
    template_id: str,
    template_data: TemplateUpdate,
    req: Request,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    permission: bool = Depends(Permission("templates_list", "UPDATE"))
):
    """Update a template"""
    service = TemplateService(db)
    
    # Calculate changes BEFORE update
    update_data = {
        "template_name": template_data.template_name,
        "description": template_data.description,
        "document_type_id": template_data.document_type_id,
        "extraction_fields": template_data.extraction_fields,
        "status_id": template_data.status_id
    }
    changes = {}
    existing_template = service.get_by_id(template_id)
    if existing_template:
        # Normalize status_id to statusCode for readable logs
        # Note: template object might be Pydantic model or dict. Service returns dict usually or ORM model.
        # Based on get_by_id implementation (assumed dict or object with dict access)
        # Assuming dict access is safe or we need logic check. 
        # Checking template_service.py usage earlier: it returns Pydantic model usually?
        # Let's check get_by_id return type if possible. 
        # But for now assuming consistency with other services returning dicts/objects.
        # Actually template_service.get_by_id returns a TemplateResponse Pydantic model often. 
        # calculate_changes handles dict or object. 
        # But we need to write to it. If it's a Pydantic model we can't write to it easily if frozen?
        # Wait, calculate_changes takes OLD obj.
        # Let's handle generic object attribute setting if dict fails.
        
        # Actually, let's just stick to the pattern. If it errors we fix.
        # But wait, templates_service.get_by_id returns a TemplateResponse?
        # Let's check templates_router.py:128 `return service.get_by_id(template_id)` -> response_model=TemplateResponse
        # So it returns something compatible.
        
        # To be safe for mixed types (dict vs obj):
        current_status_code = None
        if isinstance(existing_template, dict):
            current_status_code = existing_template.get('statusCode')
        elif hasattr(existing_template, 'statusCode'):
            current_status_code = getattr(existing_template, 'statusCode')
            
        if 'status_id' in update_data and current_status_code:
             if isinstance(existing_template, dict):
                 existing_template['status_id'] = current_status_code
             else:
                 setattr(existing_template, 'status_id', current_status_code)

        changes = ActivityService.calculate_changes(existing_template, update_data)
        
        # Rename status_id to Status
        if 'status_id' in changes:
            changes['Status'] = changes.pop('status_id')

    template = service.update(
        template_id,
        template_data.template_name,
        template_data.description,
        template_data.document_type_id,
        template_data.extraction_fields,
        template_data.status_id
    )
    
    if template:
         ActivityService.log(
            db,
            action="UPDATE",
            entity_type="template",
            entity_id=str(template_id),
            user_id=current_user.id,
            details={"name": template.template_name, "changes": changes},
            request=req,
            background_tasks=background_tasks
        )
    
    return template

@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_template(
    template_id: str,
    req: Request,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    permission: bool = Depends(Permission("templates_list", "DELETE"))
):
    """Delete a template"""
    service = TemplateService(db)
    name = service.delete(template_id)

    ActivityService.log(
        db,
        action="DELETE",
        entity_type="template",
        entity_id=str(template_id),
        user_id=current_user.id,
        details={"name": name},
        request=req,
        background_tasks=background_tasks
    )
    return {"message": "Template deleted successfully"}

@router.patch("/{template_id}/activate")
def activate_template(
    template_id: str,
    req: Request,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    permission: bool = Depends(Permission("templates_list", "UPDATE"))
):
    """Activate a template"""
    service = TemplateService(db)
    result = service.activate(template_id)
    
    ActivityService.log(
        db,
        action="ACTIVATE",
        entity_type="template",
        entity_id=str(template_id),
        user_id=current_user.id,
        request=req,
        background_tasks=background_tasks
    )
    return result

@router.patch("/{template_id}/deactivate")
def deactivate_template(
    template_id: str,
    req: Request,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    permission: bool = Depends(Permission("templates_list", "UPDATE"))
):
    """Deactivate a template"""
    service = TemplateService(db)
    result = service.deactivate(template_id)
    
    ActivityService.log(
        db,
        action="DEACTIVATE",
        entity_type="template",
        entity_id=str(template_id),
        user_id=current_user.id,
        request=req,
        background_tasks=background_tasks
    )
    return result