from fastapi import APIRouter, HTTPException, Depends, Request, BackgroundTasks
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
import re

from app.core.database import get_db
from app.services.organisations_service import OrganisationService
from app.services.activity_service import ActivityService
from app.core.permissions import Permission
from app.core.security import get_current_user
from app.models.user import User

router = APIRouter(dependencies=[Depends(get_current_user)])

# --- Schemas ---

class OrganisationCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100) # Added name field
    email: str
    username: str = Field(..., min_length=3, max_length=50)
    first_name: str = Field(..., min_length=1, max_length=50)
    middle_name: Optional[str] = Field(None, max_length=50)
    last_name: str = Field(..., min_length=1, max_length=50)
    password: str = Field(..., min_length=6) # Removing password from Create for now as UI might auto-generate or not ask
    phone_country_code: Optional[str] = None
    phone_number: Optional[str] = None
    
    @field_validator('email')
    @classmethod
    def validate_email(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError('Email cannot be empty')
        if not re.match(r'^[^\s@]+@[^\s@]+\.[^\s@]+$', v):
            raise ValueError('Invalid email format')
        return v.strip().lower()
    
    @field_validator('username')
    @classmethod
    def validate_username(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError('Username cannot be empty')
        return v.strip()

class OrganisationUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100) # Added name field
    email: Optional[str] = None
    username: Optional[str] = Field(None, min_length=3, max_length=50)
    first_name: Optional[str] = Field(None, min_length=1, max_length=50)
    middle_name: Optional[str] = Field(None, max_length=50)
    last_name: Optional[str] = Field(None, min_length=1, max_length=50)
    phone_country_code: Optional[str] = None
    phone_number: Optional[str] = None
    status_id: Optional[str] = None
    
    @field_validator('email')
    @classmethod
    def validate_email(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            if not v.strip():
                raise ValueError('Email cannot be empty')
            if not re.match(r'^[^\s@]+@[^\s@]+\.[^\s@]+$', v):
                raise ValueError('Invalid email format')
            return v.strip().lower()
        return v

class OrganisationResponse(BaseModel):
    id: str
    email: str
    username: str
    first_name: Optional[str]
    middle_name: Optional[str]
    last_name: Optional[str]
    phone_country_code: Optional[str]
    phone_number: Optional[str]
    status_id: Optional[int]
    statusCode: Optional[str]
    created_at: Optional[str]
    updated_at: Optional[str]
    name: str

    class Config:
        from_attributes = True

class OrganisationListResponse(BaseModel):
    organisations: List[OrganisationResponse]
    total: int
    page: int
    page_size: int

# --- Endpoints ---

@router.get("/stats")
def get_organisation_stats(
    db: Session = Depends(get_db),
    permission: bool = Depends(Permission("users", "READ")) # Reusing users permission for now or create new module? Assuming 'users' permission covers this as it's similar management
):
    return OrganisationService.get_organisation_stats(db)

@router.get("", response_model=OrganisationListResponse)
@router.get("/", response_model=OrganisationListResponse)
def get_organisations(
    page: int = 1,
    page_size: int = 10,
    search: Optional[str] = None,
    status_id: Optional[str] = None,
    db: Session = Depends(get_db),
    permission: bool = Depends(Permission("users", "READ"))
):
    orgs, total = OrganisationService.get_organisations(page, page_size, search, status_id, db)
    return OrganisationListResponse(
    organisations=[
        OrganisationResponse.model_validate(o, from_attributes=True)
        for o in orgs],
        total=total,
        page=page,
        page_size=page_size
    )

@router.post("", response_model=OrganisationResponse)
@router.post("/", response_model=OrganisationResponse)
def create_organisation(
    org: OrganisationCreate,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    permission: bool = Depends(Permission("users", "CREATE"))
):
    if OrganisationService.check_email_exists(org.email, None, db):
        raise HTTPException(status_code=400, detail="Email already exists")
    if OrganisationService.check_username_exists(org.username, None, db):
        raise HTTPException(status_code=400, detail="Username already exists")
        
    org_data = org.model_dump()
    created_org = OrganisationService.create_organisation(org_data, db)

    ActivityService.log(
        db=db,
        action="CREATE",
        entity_type="organisation",
        entity_id=str(created_org["id"]),
        user_id=current_user.id,
        details={"name": created_org["name"]},
        request=request,
        background_tasks=background_tasks
    )

    return OrganisationResponse(**created_org)



@router.put("/{org_id}", response_model=OrganisationResponse)
def update_organisation(
    org_id: str,
    org: OrganisationUpdate,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    permission: bool = Depends(Permission("users", "UPDATE"))
):
    if org.email and OrganisationService.check_email_exists(org.email, org_id, db):
        raise HTTPException(status_code=400, detail="Email already exists")
    if org.username and OrganisationService.check_username_exists(org.username, org_id, db):
        raise HTTPException(status_code=400, detail="Username already exists")
        
    org_data = org.model_dump(exclude_unset=True)
    
    # Capture changes logic could go here similarly to other modules
    
    updated_org = OrganisationService.update_organisation(org_id, org_data, db)
    if not updated_org:
        raise HTTPException(status_code=404, detail="Organisation not found")

    ActivityService.log(
        db=db,
        action="UPDATE",
        entity_type="organisation",
        entity_id=org_id,
        user_id=current_user.id,
        details={"name": updated_org["name"]},
        request=request,
        background_tasks=background_tasks
    )

    return OrganisationResponse(**updated_org)



@router.post("/{org_id}/deactivate", response_model=OrganisationResponse)
def deactivate_organisation(
    org_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    permission: bool = Depends(Permission("users", "DELETE"))
):
    deactivated_org = OrganisationService.deactivate_organisation(org_id, db)
    if not deactivated_org:
        raise HTTPException(status_code=404, detail="Organisation not found")

    ActivityService.log(
        db=db,
        action="DEACTIVATE",
        entity_type="organisation",
        entity_id=org_id,
        user_id=current_user.id,
        details={"name": deactivated_org["name"]},
        request=request,
        background_tasks=background_tasks
    )

    return OrganisationResponse(**deactivated_org)


class ChangePasswordRequest(BaseModel):
    new_password: str = Field(..., min_length=6, description="New password for the organisation")

@router.put("/{org_id}/change-password")
async def change_organisation_password(
    org_id: str,
    password_request: ChangePasswordRequest,
    db: Session = Depends(get_db),
    permission: bool = Depends(Permission("users", "UPDATE")),
    background_tasks: BackgroundTasks = None,
    request: Request = None,
    current_user: User = Depends(get_current_user)
):
    success = OrganisationService.change_password(org_id, password_request.new_password, db)
    if not success:
        raise HTTPException(status_code=404, detail="Organisation not found")
        
    # Log activity
    ActivityService.log(
        db=db,
        action="CHANGE_PASSWORD",
        entity_type="organisation",
        entity_id=org_id,
        user_id=current_user.id,
        request=request,
        background_tasks=background_tasks
    )
        
    return {"message": "Password changed successfully"}
