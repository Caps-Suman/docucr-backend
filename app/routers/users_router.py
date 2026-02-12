from fastapi import APIRouter, HTTPException, Depends, Request, BackgroundTasks
from app.models.organisation import Organisation
from app.services.activity_service import ActivityService
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
from fastapi import Query
import re

from app.core.database import get_db
from app.services.user_service import UserService
from app.core.permissions import Permission
from app.core.security import get_current_user
from app.models.user import User

router = APIRouter()

class AssignClientsRequest(BaseModel):
    client_ids: List[str]
    assigned_by: Optional[str] = None

class OrganisationResponse(BaseModel):
    id: str
    email: str
    username: str

class UserCreate(BaseModel):
    email: str
    username: str = Field(..., min_length=3, max_length=50)
    first_name: str = Field(..., min_length=1, max_length=50)
    middle_name: Optional[str] = Field(None, max_length=50)
    last_name: str = Field(..., min_length=1, max_length=50)
    password: str = Field(..., min_length=6)
    phone_country_code: Optional[str] = None
    phone_number: Optional[str] = None
    role_ids: List[str] = []
    supervisor_id: Optional[str] = None
    client_id: Optional[str] = None
    
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

class UserUpdate(BaseModel):
    email: Optional[str] = None
    username: Optional[str] = Field(None, min_length=3, max_length=50)
    first_name: Optional[str] = Field(None, min_length=1, max_length=50)
    middle_name: Optional[str] = Field(None, max_length=50)
    last_name: Optional[str] = Field(None, min_length=1, max_length=50)
    phone_country_code: Optional[str] = None
    phone_number: Optional[str] = None
    status_id: Optional[str] = None
    role_ids: Optional[List[str]] = None
    supervisor_id: Optional[str] = None
    client_id: Optional[str] = None

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

class UserResponse(BaseModel):
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
    is_superuser: bool
    roles: List[dict]
    supervisor_id: Optional[str]
    client_count: int = 0
    created_by_name: Optional[str] = None
    organisation_name: Optional[str] = None
    client_id: Optional[str] = None
    client_name: Optional[str] = None
    
    class Config:
        from_attributes = True

class UserListResponse(BaseModel):
    users: List[UserResponse]
    total: int
    page: int
    page_size: int

@router.get("", response_model=UserListResponse)
@router.get("/", response_model=UserListResponse)
async def get_users(
    page: int = 1,
    page_size: int = 25,
    search: Optional[str] = None,
    status_id: Optional[str] = None,
    role_id: Optional[List[str]] = Query(None),
    organisation_id: Optional[List[str]] = Query(None),
    client_id: Optional[List[str]] = Query(None),
    created_by: Optional[List[str]] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    users, total = UserService.get_users(
        page, 
        page_size, 
        search, 
        status_id, 
        db, 
        current_user,
        role_id=role_id,
        organisation_id=organisation_id,
        client_id=client_id,
        created_by=created_by
    )
    return UserListResponse(
        users=[UserResponse(**user) for user in users],
        total=total,
        page=page,
        page_size=page_size
    )

class CreatorResponse(BaseModel):
    id: str
    first_name: str
    last_name: str
    username: str
    organisation_name: Optional[str] = None

@router.get("/creators", response_model=List[CreatorResponse])
async def get_creators(
    search: Optional[str] = None,
    organisation_id: Optional[List[str]] = Query(None),
    client_id: Optional[List[str]] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Lightweight endpoint to fetch potential creators for filters.
    Returns only ID, Name, Username and Organisation Name.
    """
    return UserService.get_creators(
        search, 
        db, 
        current_user,
        organisation_id=organisation_id,
        client_id=client_id
    )

# @router.get("/me", response_model=UserResponse)
# async def get_current_user_profile(
#     current_user: User = Depends(get_current_user),
#     db: Session = Depends(get_db)
# ):
#     return UserService._format_user_response(current_user, db)
@router.get("/me", response_model=UserResponse)
async def get_current_user_profile(
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if isinstance(current_user, Organisation):
        return {
            "id": current_user.id,
            "email": current_user.email,
            "username": current_user.username,
            "first_name": current_user.first_name,
            "middle_name": current_user.middle_name,
            "last_name": current_user.last_name,
            "phone_country_code": current_user.phone_country_code,
            "phone_number": current_user.phone_number,
            "status_id": current_user.status_id,
            "statusCode": None,
            "is_superuser": False,
            "roles": [],
            "supervisor_id": None,
            "client_count": 0,
            "created_by_name": None,
            "organisation_name": current_user.username
        }

    return UserService._format_user_response_for_me(current_user, db)

@router.get("/stats")
async def get_user_stats(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return UserService.get_user_stats(db, current_user)

@router.get("/by-role", response_model=List[UserResponse])
async def get_users_by_role(
    role_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    users = UserService.get_users_by_role(role_id, db, current_user)
    return [UserResponse(**u) for u in users]

@router.get("/email/{email}", response_model=UserResponse)
async def get_user_by_email(
    email: str, 
    db: Session = Depends(get_db)
):
    user = UserService.get_user_by_email(email, db)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return UserResponse(**user)

@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: str, 
    db: Session = Depends(get_db)
):
    user = UserService.get_user_by_id(user_id, db)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return UserResponse(**user)

@router.post("/", response_model=UserResponse)
async def create_user(
    user: UserCreate, 
    db: Session = Depends(get_db),
    permission: bool = Depends(Permission("user_module", "CREATE")),
    background_tasks: BackgroundTasks = None,
    request: Request = None,
    current_user: User = Depends(get_current_user)
):
    if UserService.check_email_exists(user.email, None, db):
        raise HTTPException(status_code=400, detail="Email already exists")
    if UserService.check_username_exists(user.username, None, db):
        raise HTTPException(status_code=400, detail="Username already exists")
    
    user_data = user.model_dump()
    created_user = UserService.create_user(user_data, db, current_user)
    
    # Log activity
    ActivityService.log(
        db=db,
        action="CREATE",
        entity_type="user",
        entity_id=created_user.id,
        user_id=current_user.id,
        details={"username": created_user.username, "email": created_user.email},
        request=request,
        background_tasks=background_tasks
    )
    
    return UserResponse(
    **UserService._format_user_response(created_user, db)
    )

@router.put("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: str, 
    user: UserUpdate, 
    db: Session = Depends(get_db),
    permission: bool = Depends(Permission("user_module", "UPDATE")),
    background_tasks: BackgroundTasks = None,
    request: Request = None,
    current_user: User = Depends(get_current_user)
):
    if user.email and UserService.check_email_exists(user.email, user_id, db):
        raise HTTPException(status_code=400, detail="Email already exists")
    if user.username and UserService.check_username_exists(user.username, user_id, db):
        raise HTTPException(status_code=400, detail="Username already exists")
    if user.phone_number:
        if not user.phone_number.isdigit():
            raise HTTPException(status_code=400, detail="Phone number must contain only digits")
        if len(user.phone_number) < 10 or len(user.phone_number) > 15:
            raise HTTPException(status_code=400, detail="Phone number must be 10-15 digits")
    
    user_data = user.model_dump(exclude_unset=True)
    roles_changed = 'role_ids' in user_data

    
    # Capture potential changes before update
    existing_user = UserService.get_user_by_id(user_id, db)
    changes = ActivityService.calculate_changes(existing_user, user_data) or {}

    if existing_user:
        # Normalize status_id to statusCode for readable logs
        if 'status_id' in user_data and existing_user.get('statusCode'):
            existing_user['status_id'] = existing_user['statusCode']
            
        changes = ActivityService.calculate_changes(existing_user, user_data, exclude=["password"]) or {}
        if not changes and not roles_changed:
            raise HTTPException(400, "No changes provided")

        if roles_changed:
            changes['Role'] = 'Updated'
        # Rename status_id to Status
        if 'status_id' in changes:
            changes['Status'] = changes.pop('status_id')

    updated_user = UserService.update_user(user_id, user_data, db, current_user)
    if not updated_user:
        raise HTTPException(status_code=404, detail="User not found")
        
    # Log activity
    full_name = f"{updated_user.get('first_name', '')} {updated_user.get('last_name', '')}".strip() or updated_user.get('username')
    ActivityService.log(
        db=db,
        action="UPDATE",
        entity_type="user",
        entity_id=user_id,
        user_id=current_user.id,
        details={"name": full_name, "changes": changes},
        request=request,
        background_tasks=background_tasks
    )
        
    return UserResponse(**updated_user)

@router.post("/{user_id}/activate", response_model=UserResponse)
async def activate_user(
    user_id: str,
    db: Session = Depends(get_db),
    background_tasks: BackgroundTasks = None,
    request: Request = None,
    current_user = Depends(get_current_user)
):
    if str(current_user.id) == str(user_id):
        raise HTTPException(403, "You cannot activate yourself")

    target_user = db.query(User).filter(User.id == user_id).first()
    if not target_user:
        raise HTTPException(404, "User not found")

    if target_user.is_superuser:
        raise HTTPException(403, "Cannot modify super admin")

    if not UserService.can_manage_user(current_user, target_user):
        raise HTTPException(403, "Not allowed to activate this user")

    user = UserService.activate_user(user_id, db, current_user)
    if not user:
        raise HTTPException(400, "Activation failed")

    ActivityService.log(
        db=db,
        action="ACTIVATE",
        entity_type="user",
        entity_id=user_id,
        user_id=current_user.id,
        request=request,
        background_tasks=background_tasks
    )

    return UserResponse(**user)



@router.post("/{user_id}/deactivate", response_model=UserResponse)
async def deactivate_user(
    user_id: str,
    db: Session = Depends(get_db),
    background_tasks: BackgroundTasks = None,
    request: Request = None,
    current_user = Depends(get_current_user)
):
    # block self
    if isinstance(current_user, User) and str(current_user.id) == user_id:
        raise HTTPException(403, "You cannot deactivate yourself")

    target_user = db.query(User).filter(User.id == user_id).first()
    if not target_user:
        raise HTTPException(404, "User not found")

    if target_user.is_superuser:
        raise HTTPException(403, "Cannot deactivate super admin")

    # ---- PERMISSION ----
    if not UserService.can_manage_user(current_user, target_user):
        raise HTTPException(403, "Not allowed to deactivate this user")

    user = UserService.deactivate_user(user_id, db, current_user)
    if not user:
        raise HTTPException(400, "Deactivate failed")

    ActivityService.log(
        db=db,
        action="DEACTIVATE",
        entity_type="user",
        entity_id=user_id,
        user_id=getattr(current_user, "id", None),
        request=request,
        background_tasks=background_tasks
    )

    return UserResponse(**user)


class ChangePasswordRequest(BaseModel):
    new_password: str = Field(..., min_length=6, description="New password for the user")

@router.post("/{user_id}/change-password")
async def change_user_password(
    user_id: str, 
    password_request: ChangePasswordRequest, 
    db: Session = Depends(get_db),
    permission: bool = Depends(Permission("user_module", "ADMIN")),
    background_tasks: BackgroundTasks = None,
    request: Request = None,
    current_user: User = Depends(get_current_user)
):
    success = UserService.change_password(user_id, password_request.new_password, db)
    if not success:
        raise HTTPException(status_code=404, detail="User not found")
        
    # Log activity
    ActivityService.log(
        db=db,
        action="CHANGE_PASSWORD",
        entity_type="user",
        entity_id=user_id,
        user_id=current_user.id,
        request=request,
        background_tasks=background_tasks
    )
        
    return {"message": "Password changed successfully"}

from app.routers.clients_router import ClientResponse

@router.get("/{user_id}/clients", response_model=List[ClientResponse])
async def get_user_clients(
    user_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get clients mapped to a user"""
    # Check permission or visibility? 
    # Assuming standard visibility rules apply or admin access.
    # For now, allowing READ permission on user_module to see clients.
    clients = UserService.get_user_clients(user_id, db)
    return clients

@router.post("/{user_id}/clients")
async def map_clients_to_user(
    user_id: str,
    request: AssignClientsRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    permission: bool = Depends(Permission("user_module", "UPDATE")) # Mapping clients is an update action
):
    """Map clients to a user"""
    assigned_by_id = None
    if isinstance(current_user, User):
        assigned_by_id = str(current_user.id)
    
    UserService.map_clients_to_user(user_id, request.client_ids, assigned_by_id, db)
    
    # Log activity
    ActivityService.log(
        db=db,
        action="UPDATE",
        entity_type="user",
        entity_id=user_id,
        user_id=current_user.id,
        details={"action": "map_clients", "client_ids": request.client_ids}
    )
    
    return {"message": "Clients mapped successfully"}

class UnassignClientsRequest(BaseModel):
    user_id: str
    client_ids: List[str]

@router.post("/unassign-clients")
async def unassign_clients(
    request: UnassignClientsRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    permission: bool = Depends(Permission("user_module", "UPDATE")) # Unassigning is an update action
):
    """Unassign one or more clients from a user"""
    UserService.unassign_clients_from_user(request.user_id, request.client_ids, db)
    
    # Log activity
    ActivityService.log(
        db=db,
        action="UPDATE",
        entity_type="user",
        entity_id=request.user_id,
        user_id=current_user.id,
        details={"action": "unassign_clients", "client_ids": request.client_ids}
    )
    
    return {"message": "Clients unassigned successfully"}
