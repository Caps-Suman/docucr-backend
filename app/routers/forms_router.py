from fastapi import APIRouter, HTTPException, Depends, Request, BackgroundTasks
from app.services.activity_service import ActivityService
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from app.core.database import get_db
from app.services.form_service import FormService
from app.routers.auth_router import get_current_user
from app.core.permissions import Permission

router = APIRouter()

class FormFieldSchema(BaseModel):
    field_type: str
    label: str
    placeholder: Optional[str] = None
    required: bool = False
    options: Optional[List[str]] = None
    validation: Optional[Dict[str, Any]] = None
    is_system: Optional[bool] = False
    default_value: Optional[Any] = None   # 👈 ADD THIS
class FormCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    fields: List[FormFieldSchema] = []

class FormUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    status_id: Optional[str] = None
    fields: Optional[List[FormFieldSchema]] = None

class FormResponse(BaseModel):
    id: str
    name: str
    description: Optional[str]
    status_id: Optional[int]
    statusCode: Optional[str]
    created_at: Any
    fields_count: Optional[int] = 0

class FormDetailResponse(BaseModel):
    id: str
    name: str
    description: Optional[str]
    status_id: Optional[int]
    created_at: Any
    fields: List[Dict[str, Any]]

class FormListResponse(BaseModel):
    forms: List[FormResponse]
    total: int
    page: int
    page_size: int

@router.get("", response_model=FormListResponse)
@router.get("/", response_model=FormListResponse)
def get_forms(
    page: int = 1,
    page_size: int = 10,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    forms, total = FormService.get_forms(page, page_size, db)
    return FormListResponse(
        forms=forms,
        total=total,
        page=page,
        page_size=page_size
    )

@router.get("/stats")
def get_form_stats(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    return FormService.get_form_stats(db)

@router.get("/active", response_model=FormDetailResponse)
def get_active_form(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    form = FormService.get_active_form(db)
    if not form:
        raise HTTPException(status_code=404, detail="No active form found")
    return form

@router.get("/{form_id}", response_model=FormDetailResponse)
def get_form(
    form_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    form = FormService.get_form_by_id(form_id, db)
    if not form:
        raise HTTPException(status_code=404, detail="Form not found")
    return form

@router.post("", response_model=FormDetailResponse)
@router.post("/", response_model=FormDetailResponse)
def create_form(
    form: FormCreate,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    permission: bool = Depends(Permission("templates", "CREATE"))
):
    if FormService.check_form_name_exists(form.name, None, db):
        raise HTTPException(status_code=400, detail="Form with this name already exists")
    
    try:
        form_data = form.model_dump()
        created_form = FormService.create_form(form_data, current_user.id, db)
        
        ActivityService.log(
            db=db,
            action="CREATE",
            entity_type="form",
            entity_id=created_form["id"],
            user_id=current_user.id,
            details={"name": created_form["name"]},
            request=request,
            background_tasks=background_tasks
        )
        
        return created_form
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.put("/{form_id}", response_model=FormDetailResponse)
def update_form(
    form_id: str,
    form: FormUpdate,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    permission: bool = Depends(Permission("templates", "UPDATE"))
):
    if form.name and FormService.check_form_name_exists(form.name, form_id, db):
        raise HTTPException(status_code=400, detail="Form with this name already exists")
    
    try:
        form_data = form.model_dump(exclude_unset=True)
        
        # Calculate changes BEFORE update
        changes = {}
        existing_form_dict = FormService.get_form_by_id(form_id, db)
        if existing_form_dict:
            # Normalize status_id to statusCode for readable logs
            if 'status_id' in form_data and existing_form_dict.get('statusCode'):
                existing_form_dict['status_id'] = existing_form_dict['statusCode']
                
            changes = ActivityService.calculate_changes(existing_form_dict, form_data, exclude=["fields"])
            
            # Rename status_id to Status
            if 'status_id' in changes:
                changes['Status'] = changes.pop('status_id')

        updated_form = FormService.update_form(form_id, form_data, db)
        if not updated_form:
            raise HTTPException(status_code=404, detail="Form not found")
            
        ActivityService.log(
            db=db,
            action="UPDATE",
            entity_type="form",
            entity_id=form_id,
            user_id=current_user.id,
            details={"name": updated_form.get('name'), "changes": changes},
            request=request,
            background_tasks=background_tasks
        )
            
        return updated_form
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.delete("/{form_id}")
def delete_form(
    form_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    permission: bool = Depends(Permission("templates", "DELETE"))
):
    """Delete a form"""
    name = FormService.delete_form(form_id, db)
    if not name:
        raise HTTPException(status_code=404, detail="Form not found")
        
    ActivityService.log(
        db=db,
        action="DELETE",
        entity_type="form",
        entity_id=form_id,
        user_id=current_user.id,
        details={"name": name},
        request=request,
        background_tasks=background_tasks
    )
    
    return {"message": "Form deleted successfully"}
