from fastapi import APIRouter, HTTPException, Depends, Request, BackgroundTasks
from app.services.activity_service import ActivityService
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
import re

from app.core.database import get_db
from app.services.user_service import UserService
from app.core.permissions import Permission
from app.core.security import get_current_user
from app.models.user import User

router = APIRouter()

class AssignClientsRequest(BaseModel):
    client_ids: List[str]
    assigned_by: str

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
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    users, total = UserService.get_users(page, page_size, search, status_id, db, current_user)
    return UserListResponse(
        users=[UserResponse(**user) for user in users],
        total=total,
        page=page,
        page_size=page_size
    )

@router.get("/me", response_model=UserResponse)
async def get_current_user_profile(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return UserService._format_user_response(current_user, db)

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
    created_user = UserService.create_user(user_data, db)
    
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

    updated_user = UserService.update_user(user_id, user_data, db)
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
    permission: bool = Depends(Permission("user_module", "UPDATE")),
    background_tasks: BackgroundTasks = None,
    request: Request = None,
    current_user: User = Depends(get_current_user)
):
    # ---- SELF-ACTION BLOCK ----
    if current_user.id == user_id:
        raise HTTPException(
            status_code=403,
            detail="You cannot activate your own account"
        )

    # ---- ROLE CHECK ----
    role_names = [role.name for role in current_user.roles]
    is_admin = (
        current_user.is_superuser or
        "ADMIN" in role_names or
        "SUPER_ADMIN" in role_names
    )

    if not is_admin:
        raise HTTPException(
            status_code=403,
            detail="You are not allowed to activate users"
        )

    # ---- TARGET USER VALIDATION ----
    target_user = db.query(User).filter(User.id == user_id).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")

    if target_user.is_superuser:
        raise HTTPException(
            status_code=403,
            detail="Super admin cannot be activated via API"
        )

    # ---- ACTIVATE ----
    user = UserService.activate_user(user_id, db)
    if not user:
        raise HTTPException(status_code=400, detail="Cannot activate user")

    # ---- ACTIVITY LOG ----
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
    permission: bool = Depends(Permission("user_module", "UPDATE")),
    background_tasks: BackgroundTasks = None,
    request: Request = None,
    current_user: User = Depends(get_current_user)
):
    # ---- SELF-DEACTIVATION BLOCK ----
    if current_user.id == user_id:
        raise HTTPException(
            status_code=403,
            detail="You cannot deactivate your own account"
        )

    # ---- ROLE CHECK ----
    role_names = [role.name for role in current_user.roles]
    is_admin = (
        current_user.is_superuser or
        "ADMIN" in role_names or
        "SUPER_ADMIN" in role_names
    )

    if not is_admin:
        raise HTTPException(
            status_code=403,
            detail="You are not allowed to deactivate users"
        )

    # ---- TARGET USER SAFETY ----
    target_user = db.query(User).filter(User.id == user_id).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")

    if target_user.is_superuser:
        raise HTTPException(
            status_code=403,
            detail="Super admin cannot be deactivated"
        )

    # ---- DEACTIVATE ----
    user = UserService.deactivate_user(user_id, db)
    if not user:
        raise HTTPException(status_code=400, detail="Cannot deactivate user")

    # ---- ACTIVITY LOG ----
    ActivityService.log(
        db=db,
        action="DEACTIVATE",
        entity_type="user",
        entity_id=user_id,
        user_id=current_user.id,
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
    UserService.map_clients_to_user(user_id, request.client_ids, request.assigned_by, db)
    
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
