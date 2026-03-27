from fastapi import APIRouter, HTTPException, Depends, Request, BackgroundTasks
from sqlalchemy import and_, func, or_
from app.models.organisation import Organisation
from app.models.role import Role
from app.models.status import Status
from app.models.user_role import UserRole
from app.services.activity_service import ActivityService
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field, field_validator, validator
from typing import Optional, List
from fastapi import Query
import re
from app.core.database import get_db
from app.services.role_service import RoleService
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
    password: str = Field(..., min_length=8)
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
    
    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        v = v.strip()

        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")

        if not re.search(r"[A-Z]", v):
            raise ValueError("Must include uppercase letter")

        if not re.search(r"[a-z]", v):
            raise ValueError("Must include lowercase letter")

        if not re.search(r"\d", v):
            raise ValueError("Must include number")

        if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", v):
            raise ValueError("Must include special character")

        return v

class BulkUserRow(BaseModel):
    email: str
    username: str
    first_name: str
    last_name: str
    password: str
    middle_name: Optional[str] = None
    phone_country_code: Optional[str] = None
    phone_number: Optional[str] = None
    # Internal-only fields
    role_names: Optional[str] = None   
    supervisor_email: Optional[str] = None
 
    @validator("email")
    def email_lower(cls, v):
        return v.strip().lower()
 
    @validator("username")
    def username_lower(cls, v):
        return v.strip().lower()
 
 
class BulkUserUploadRequest(BaseModel):
    user_type: str                     # "internal" | "client"
    client_id: Optional[str] = None   # Required when user_type == "client"
    users: List[BulkUserRow]
 
    @validator("user_type")
    def validate_type(cls, v):
        if v not in ("internal", "client"):
            raise ValueError('user_type must be "internal" or "client"')
        return v
 
    @validator("client_id", always=True)
    def client_required_for_client_type(cls, v, values):
        if values.get("user_type") == "client" and not v:
            raise ValueError("client_id is required when user_type is 'client'")
        return v
 
 
class FailedRow(BaseModel):
    row_index: int
    email: Optional[str]
    error: str
 
 
class BulkUserUploadResponse(BaseModel):
    created: int
    failed: int
    failed_rows: List[FailedRow]
    errors: List[str]    
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
    is_superuser: Optional[bool] = False
    roles: List[dict]
    supervisor_id: Optional[str]
    client_count: int = 0
    created_by_name: Optional[str] = None
    organisation_name: Optional[str] = None
    client_id: Optional[str] = None
    client_name: Optional[str] = None
    profile_image_url: Optional[str] = None
    
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
    is_client: Optional[bool] = Query(None),
    created_by: Optional[List[str]] = Query(None),
    db: Session = Depends(get_db),
    _: User = Depends(Permission("user_module", "READ")),   # 🔥 FIX
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
        created_by=created_by,
        is_client=is_client
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

@router.get("/me", response_model=UserResponse)
async def get_current_user_profile(
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db)
):

    return UserService._format_user_response_for_me(current_user, db)
@router.get("/by-organisation")
def get_users_by_org(
    organisation_id: str,
    search: str | None = None,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    query = db.query(User).filter(User.organisation_id == organisation_id)

    # only INTERNAL users
    query = query.filter(
        User.is_client == False,
        User.client_id.is_(None)
    )

    if search:
        query = query.filter(
            or_(
                User.first_name.ilike(f"%{search}%"),
                User.last_name.ilike(f"%{search}%"),
                User.email.ilike(f"%{search}%")
            )
        )

    users = query.limit(50).all()

    return {
        "users": [
            {
                "id": u.id,
                "first_name": u.first_name,
                "last_name": u.last_name,
                "email": u.email,
            }
            for u in users
        ]
    }
@router.get("/by-client")
def get_users_by_client(
    client_id: str,
    search: str | None = None,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    query = db.query(User).filter(User.client_id == client_id)

    if search:
        query = query.filter(
            or_(
                User.first_name.ilike(f"%{search}%"),
                User.last_name.ilike(f"%{search}%"),
                User.email.ilike(f"%{search}%")
            )
        )

    users = query.limit(50).all()

    return {
        "users": [
            {
                "id": u.id,
                "first_name": u.first_name,
                "last_name": u.last_name,
                "email": u.email,
            }
            for u in users
        ]
    }
@router.get("/share/users")
def get_share_users(
    is_client: bool,
    search: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Resolve organisation
    org_id = current_user.organisation_id

    if not org_id:
        raise HTTPException(400, "User not linked to organisation")

    active_status = db.query(Status).filter(Status.code == "ACTIVE").first()

    query = (
        db.query(User)
        .join(UserRole, UserRole.user_id == User.id)
        .join(Role, Role.id == UserRole.role_id)
        .filter(
            User.organisation_id == org_id,
            User.id != current_user.id,
            User.status_id == active_status.id
        )
    )

    # -------------------------
    # CLIENT USERS
    # -------------------------
    if is_client:
        query = query.filter(
            or_(
                User.is_client.is_(True),
                User.client_id.isnot(None)
            )
        )

    # -------------------------
    # INTERNAL USERS
    # -------------------------
    else:
        query = query.filter(
            User.is_client.is_(False),
            User.client_id.is_(None),
            ~Role.name.in_(["SUPER_ADMIN", "ORGANISATION_ADMIN"])
        )

    if search:
        query = query.filter(
            or_(
                User.first_name.ilike(f"%{search}%"),
                User.last_name.ilike(f"%{search}%"),
                User.email.ilike(f"%{search}%"),
            )
        )

    users = query.distinct().limit(50).all()

    return {
        "users": [
            {
                "id": u.id,
                "first_name": u.first_name,
                "last_name": u.last_name,
                "email": u.email,
                "roles": [
                    {"id": r.id, "name": r.name}
                    for r in u.roles
                ]
            }
            for u in users
        ]
    }

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
        entity_id=str(created_user.id),
        current_user=current_user,
        details={"username": created_user.username},
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
        current_user=current_user,
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
        user_id=current_user,
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
    new_password: str = Field(..., min_length=8, description="New password for the user")
    @field_validator("new_password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        v = v.strip()

        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")

        if not re.search(r"[A-Z]", v):
            raise ValueError("Must include uppercase letter")

        if not re.search(r"[a-z]", v):
            raise ValueError("Must include lowercase letter")

        if not re.search(r"\d", v):
            raise ValueError("Must include number")

        if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", v):
            raise ValueError("Must include special character")

        return v
@router.post("/{user_id}/change-password")
async def change_user_password(
    user_id: str, 
    password_request: ChangePasswordRequest, 
    db: Session = Depends(get_db),
    permission: bool = Depends(Permission("user_module", "ADMIN")),
    background_tasks: BackgroundTasks = None,
    request: Request = None,
    current_user = Depends(get_current_user)
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
        user_id=current_user,
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
        user_id=current_user,
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
        user_id=current_user,
        details={"action": "unassign_clients", "client_ids": request.client_ids}
    )
    
    return {"message": "Clients unassigned successfully"}


@router.post(
    "/bulk",
    response_model=BulkUserUploadResponse,
    summary="Bulk create users from CSV upload",
    tags=["Users"],
)
def bulk_create_users(
    payload: BulkUserUploadRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from sqlalchemy import func

    # ── Permission guard ───────────────────────────────────────────────────────
    is_super = UserService._ctx_is_super(current_user)
    role_names_ctx = [r.name for r in current_user.roles]
    context_org = UserService._ctx_org(current_user)

    if not (is_super or "ORGANISATION_ADMIN" in role_names_ctx or "CLIENT_ADMIN" in role_names_ctx):
        raise HTTPException(status_code=403, detail="Not permitted to bulk-create users")

    if payload.user_type == "client" and not payload.client_id:
        raise HTTPException(status_code=400, detail="client_id required for client user type")

    created_count = 0
    failed_rows: List[FailedRow] = []

    role_cache = {}
    supervisor_cache = {}
    seen_emails = set()
    seen_usernames = set()

    for idx, row in enumerate(payload.users, start=1):
        try:
            # ── ALWAYS initialize (fix crash) ───────────────────────────────
            role_ids = []
            supervisor_id = None
            supervisor = None

            UserCreate.validate_password(row.password)

            # ── Normalize (important for duplicates) ────────────────────────
            email = row.email.strip().lower()
            username = row.username.strip()

            # ── CSV duplicate check ────────────────────────────────────────
            if email in seen_emails:
                raise ValueError("Duplicate email in file")
            seen_emails.add(email)

            if username in seen_usernames:
                raise ValueError("Duplicate username in file")
            seen_usernames.add(username)

            # ── DB duplicate check ─────────────────────────────────────────
            if UserService.check_email_exists(email, None, db):
                raise ValueError(f"Email already exists: {email}")

            if UserService.check_username_exists(username, None, db):
                raise ValueError(f"Username already taken: {username}")

            # ── Base data ──────────────────────────────────────────────────
            user_data = {
                "email": email,
                "username": username,
                "first_name": row.first_name,
                "middle_name": row.middle_name,
                "last_name": row.last_name,
                "phone_country_code": row.phone_country_code,
                "phone_number": row.phone_number,
                "password": row.password,
            }

            # ==============================================================
            # CLIENT USERS
            # ==============================================================
            if payload.user_type == "client":
                user_data["client_id"] = payload.client_id

            # ==============================================================
            # INTERNAL USERS
            # ==============================================================
            else:
                # ── Resolve roles (case insensitive) ───────────────────────
                if row.role_names:
                    if row.role_names in role_cache:
                        role_ids = role_cache[row.role_names]
                    else:
                        input_roles = [r.strip() for r in row.role_names.split(";") if r.strip()]

                        # 🔥 remove duplicates from CSV input
                        input_roles = list(set(input_roles))

                        normalized_roles = [r.upper() for r in input_roles]

                        roles = db.query(Role).filter(
                            func.upper(Role.name).in_(normalized_roles),
                            Role.organisation_id == context_org
                        ).all()

                        db_role_names = [r.name.upper() for r in roles]

                        invalid_roles = set(normalized_roles) - set(db_role_names)
                        if invalid_roles:
                            raise ValueError(f"Invalid roles: {', '.join(invalid_roles)}")

                        # 🔥 ensure unique role_ids
                        role_ids = list(set([r.id for r in roles]))

                        role_cache[row.role_names] = role_ids

                # 🔥 enforce role required
                if not role_ids:
                    raise ValueError("At least one valid role is required")

                # ── Resolve supervisor ─────────────────────────────────────
                if row.supervisor_email:
                    if row.supervisor_email in supervisor_cache:
                        supervisor = supervisor_cache[row.supervisor_email]
                    else:
                        supervisor = db.query(User).filter(
                            func.lower(User.email) == row.supervisor_email.lower(),
                            User.organisation_id == context_org
                        ).first()

                        if not supervisor:
                            raise ValueError(f"Supervisor not found: {row.supervisor_email}")

                        supervisor_cache[row.supervisor_email] = supervisor

                    supervisor_id = supervisor.id

                # ── Role-supervisor validation ─────────────────────────────
                if supervisor and role_ids:
                    supervisor_role_ids = [r.id for r in supervisor.roles]

                    if not any(rid in supervisor_role_ids for rid in role_ids):
                        raise ValueError("Supervisor does not belong to required role")

                # ── Attach ────────────────────────────────────────────────
                user_data["role_ids"] = role_ids
                if supervisor_id:
                    user_data["supervisor_id"] = supervisor_id

            # ── Create user ───────────────────────────────────────────────
            UserService.create_user(user_data, db=db, current_user=current_user)
            db.commit()
            created_count += 1

        except Exception as exc:
            db.rollback()
            failed_rows.append(FailedRow(
                row_index=idx,
                email=row.email,
                error=str(exc)
            ))

    return BulkUserUploadResponse(
        created=created_count,
        failed=len(failed_rows),
        failed_rows=failed_rows,
        errors=[],
    )