from datetime import timedelta
from uuid import UUID
import uuid
from fastapi import APIRouter, HTTPException, Depends, Request, BackgroundTasks
from app.core.security import security
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
import re

from app.core.database import get_db
from app.models.organisation import Organisation
from app.models.role import Role
from app.models.user_role import UserRole
from app.services.auth_service import AuthService
from app.services.organisations_service import OrganisationService
from app.services.activity_service import ActivityService
from app.core.permissions import Permission
from app.core.security import allow_temp_superadmin, decode_token, get_current_user
from app.models.user import User
from app.services.user_service import UserService

router = APIRouter()

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
    name: str
    email: Optional[str] = None
    username: Optional[str] = None
    first_name: Optional[str] = None
    middle_name: Optional[str] = None
    last_name: Optional[str] = None
    phone_country_code: Optional[str] = None
    phone_number: Optional[str] = None
    status_id: Optional[int]
    statusCode: Optional[str]
    created_at: Optional[str]

    class Config:
        from_attributes = True

class OrganisationListResponse(BaseModel):
    organisations: List[OrganisationResponse]
    total: int
    page: int
    page_size: int

# --- Endpoints ---

@router.get("/stats")
async def get_organisation_stats(
    db: Session = Depends(get_db),
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    payload = decode_token(credentials.credentials)

    # TEMP SUPERADMIN LOGIN PHASE
    if payload.get("temp") and payload.get("superadmin"):
        return OrganisationService.get_organisation_stats(db)

    # NORMAL USERS
    current_user = get_current_user(credentials, db)
    await Permission("users", "READ")(current_user)

    return OrganisationService.get_organisation_stats(db)


@router.get("", response_model=OrganisationListResponse)
@router.get("/", response_model=OrganisationListResponse)
async def get_organisations(
    page: int = 1,
    page_size: int = 10,
    search: Optional[str] = None,
    status_id: Optional[str] = None,
    db: Session = Depends(get_db),
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    payload = decode_token(credentials.credentials)

    # TEMP SUPERADMIN FLOW
    if payload.get("temp") and payload.get("superadmin"):
        orgs, total = OrganisationService.get_organisations(page, page_size, search, status_id, db)
        return OrganisationListResponse(
            organisations=[OrganisationResponse(**o) for o in orgs],
            total=total,
            page=page,
            page_size=page_size
        )


    # NORMAL FLOW
    current_user = get_current_user(credentials, db)
    await Permission("users", "READ")(current_user)

    orgs, total = OrganisationService.get_organisations(page, page_size, search, status_id, db)
    return OrganisationListResponse(
        organisations=[OrganisationResponse(**o) for o in orgs],
        total=total,
        page=page,
        page_size=page_size
    )


from app.core.security import allow_temp_superadmin
# @router.post("/select-organisation/{org_id}")
# def select_organisation(
#     org_id: str,
#     db: Session = Depends(get_db),
#     payload=Depends(allow_temp_superadmin)
# ):
#     user = db.query(User).filter(User.email == payload["sub"]).first()
#     org = db.query(Organisation).filter(Organisation.id == org_id).first()

#     if not org:
#         raise HTTPException(404, "Organisation not found")

#     superadmin_role = db.query(Role).filter(Role.name == "SUPER_ADMIN").first()
#     if not superadmin_role:
#         raise HTTPException(500, "SUPER_ADMIN role missing")

#     tokens = AuthService.generate_tokens(
#         email=user.email,
#         role_id=str(superadmin_role.id),
#         organisation_id=org_id
#     )

#     return {
#         **tokens,
#         "organisation": {
#             "id": org.id,
#             "name": org.name
#         }
#     }
@router.post("/select-organisation/{org_id}")
def select_organisation(
    org_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    if not current_user.is_superuser:
        raise HTTPException(403, "Only superadmin")

    user = db.query(User).filter(User.email == current_user.email).first()
    org = db.query(Organisation).filter(Organisation.id == org_id).first()

    if not org:
        raise HTTPException(404, "Organisation not found")

    superadmin_role = db.query(Role).filter(Role.name == "SUPER_ADMIN").first()

    tokens = AuthService.generate_tokens(
        email=user.email,
        role_id=str(superadmin_role.id),
        organisation_id=org_id,
        is_superadmin=True
    )

    return {
        **tokens,
        "organisation": {
            "id": org.id,
            "name": org.name
        }
    }    

@router.get("/{org_id}")
def get_org(org_id: str, db: Session = Depends(get_db)):
    org = OrganisationService.get_organisation_by_id(org_id, db)
    if not org:
        raise HTTPException(404, "Organisation not found")
    return org

@router.post("/clear-organisation")
def clear_org_context(
    current_user = Depends(get_current_user)
):
    if not current_user.is_superuser:
        raise HTTPException(403, "Only superadmin")

    tokens = AuthService.generate_tokens(
        email=current_user.email,
        role_id=current_user.context_role_id,
        organisation_id=None
    )

    return tokens

@router.post("/exit-organisation")
def exit_org(payload=Depends(get_current_user)):
    if not payload.context_is_superadmin:
        raise HTTPException(403)

    from app.core.security import create_access_token
    from datetime import timedelta

    temp_token = create_access_token(
        data={
            "sub": payload.email,
            "temp": True,
            "superadmin": True
        },
        expires_delta=timedelta(minutes=30)
    )

    return {
        "access_token": temp_token,
        "token_type": "bearer",
        "user": {
            "id": payload.id,
            "email": payload.email,
            "first_name": payload.first_name,
            "last_name": payload.last_name,
            "is_superuser": True,
            "profile_image_url": payload.profile_image_url
        }
    }


@router.post("", response_model=OrganisationResponse)
@router.post("/", response_model=OrganisationResponse)
async def create_organisation(
    org: OrganisationCreate,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    payload = decode_token(credentials.credentials)

    # TEMP SUPERADMIN FLOW
    if not (payload.get("temp") and payload.get("superadmin")):
        current_user = get_current_user(credentials, db)
        await Permission("users", "CREATE")(current_user)
    else:
        current_user = None

    if UserService.check_email_exists(org.email, None, db):
        raise HTTPException(status_code=400, detail="Email already exists")
    if UserService.check_username_exists(org.username, None, db):
        raise HTTPException(status_code=400, detail="Username already exists")

    org_data = org.model_dump()
    created_org = OrganisationService.create_organisation(org_data, db)

    ActivityService.log(
        db=db,
        action="CREATE",
        entity_type="organisation",
        entity_id=str(created_org["id"]),
        current_user=current_user,
        details={"name": created_org["name"]},
        request=request,
        background_tasks=background_tasks
    )

    return OrganisationResponse(**created_org)


@router.put("/{org_id}", response_model=OrganisationResponse)
async def update_organisation(
    org_id: str,
    org: OrganisationUpdate,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    payload = decode_token(credentials.credentials)

    if not (payload.get("temp") and payload.get("superadmin")):
        current_user = get_current_user(credentials, db)
        await Permission("users", "UPDATE")(current_user)
    else:
        current_user = None

    # if org.email and UserService.check_email_exists(org.email, org_id, db):
    #     raise HTTPException(status_code=400, detail="Email already exists")
    # if org.username and UserService.check_username_exists(org.username, org_id, db):
    #     raise HTTPException(status_code=400, detail="Username already exists")

    org_data = org.model_dump(exclude_unset=True)
    updated_org = OrganisationService.update_organisation(org_id, org_data, db)

    if not updated_org:
        raise HTTPException(status_code=404, detail="Organisation not found")

    ActivityService.log(
        db=db,
        action="UPDATE",
        entity_type="organisation",
        entity_id=org_id,
        current_user=current_user,
        details={"name": updated_org["name"]},
        request=request,
        background_tasks=background_tasks
    )

    return OrganisationResponse(**updated_org)


@router.post("/{org_id}/deactivate", response_model=OrganisationResponse)
async def deactivate_organisation(
    org_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    payload = decode_token(credentials.credentials)

    if not (payload.get("temp") and payload.get("superadmin")):
        current_user = get_current_user(credentials, db)
        await Permission("users", "DELETE")(current_user)
    else:
        current_user = None

    deactivated_org = OrganisationService.deactivate_organisation(org_id, db)

    if not deactivated_org:
        raise HTTPException(status_code=404, detail="Organisation not found")

    ActivityService.log(
        db=db,
        action="DEACTIVATE",
        entity_type="organisation",
        entity_id=org_id,
        current_user=current_user,
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
    request: Request = None,
    background_tasks: BackgroundTasks = None,
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    payload = decode_token(credentials.credentials)

    if not (payload.get("temp") and payload.get("superadmin")):
        current_user = get_current_user(credentials, db)
        await Permission("users", "UPDATE")(current_user)
    else:
        current_user = None

    success = OrganisationService.change_password(org_id, password_request.new_password, db)

    if not success:
        raise HTTPException(status_code=404, detail="Organisation not found")

    ActivityService.log(
        db=db,
        action="CHANGE_PASSWORD",
        entity_type="organisation",
        entity_id=org_id,
        current_user=current_user,
        request=request,
        background_tasks=background_tasks
    )

    return {"message": "Password changed successfully"}

@router.post("/{org_id}/activate", response_model=OrganisationResponse)
async def activate_organisation(
    org_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    payload = decode_token(credentials.credentials)

    # TEMP SUPERADMIN FLOW (before org selection)
    if not (payload.get("temp") and payload.get("superadmin")):
        current_user = get_current_user(credentials, db)
        await Permission("users", "UPDATE")(current_user)
    else:
        current_user = None

    activated_org = OrganisationService.activate_organisation(org_id, db)

    if not activated_org:
        raise HTTPException(status_code=404, detail="Organisation not found")

    ActivityService.log(
        db=db,
        action="ACTIVATE",
        entity_type="organisation",
        entity_id=org_id,
        current_user=current_user,
        details={"name": activated_org["name"]},
        request=request,
        background_tasks=background_tasks
    )

    return OrganisationResponse(**activated_org)
