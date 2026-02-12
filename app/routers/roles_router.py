from fastapi import APIRouter, HTTPException, Depends, Request, BackgroundTasks, Query
from app.services.activity_service import ActivityService
from app.models.user import User
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.permissions import Permission
from app.services.role_service import RoleService

router = APIRouter(dependencies=[Depends(get_current_user)])

class ModulePermission(BaseModel):
    module_id: Optional[str] = None
    submodule_id: Optional[str] = None
    privilege_id: str

class RoleCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)
    description: Optional[str] = Field(None, max_length=300)
    modules: Optional[List[ModulePermission]] = []
    
    @field_validator('name')
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError('Role name cannot be empty')
        if len(v.strip()) > 50:
            raise ValueError('Role name cannot exceed 50 characters')
        return v.strip()
    
    @field_validator('description')
    @classmethod
    def validate_description(cls, v: Optional[str]) -> Optional[str]:
        if v and len(v.strip()) > 300:
            raise ValueError('Description cannot exceed 300 characters')
        return v.strip() if v else None

class RoleUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=50)
    description: Optional[str] = Field(None, max_length=300)
    status_id: Optional[str] = None
    modules: Optional[List[ModulePermission]] = None
    
    @field_validator('name')
    @classmethod
    def validate_name(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            if not v.strip():
                raise ValueError('Role name cannot be empty')
            if len(v.strip()) > 50:
                raise ValueError('Role name cannot exceed 50 characters')
            return v.strip()
        return v
    
    @field_validator('description')
    @classmethod
    def validate_description(cls, v: Optional[str]) -> Optional[str]:
        if v and len(v.strip()) > 300:
            raise ValueError('Description cannot exceed 300 characters')
        return v.strip() if v else None

class RoleResponse(BaseModel):
    id: str
    name: str
    description: Optional[str]
    status_id: Optional[int]
    statusCode: Optional[str]
    can_edit: bool
    users_count: int
    created_by_name: Optional[str] = None
    organisation_name: Optional[str] = None

    class Config:
        from_attributes = True

class RoleUserResponse(BaseModel):
    id: str
    name: str
    email: str
    phone: Optional[str]

class UserListResponse(BaseModel):
    items: List[RoleUserResponse]
    total: int
    page: int
    page_size: int

class RoleListResponse(BaseModel):
    roles: List[RoleResponse]
    total: int
    page: int
    page_size: int

@router.get("/assignable", response_model=RoleListResponse)
async def get_assignable_roles(
    page: int = 1,
    page_size: int = 10,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    permission: bool = Depends(Permission("role_module", "READ"))
):
    roles, total = RoleService.get_assignable_roles(page, page_size, db, current_user)
    return RoleListResponse(
        roles=[RoleResponse(**role) for role in roles],
        total=total,
        page=page,
        page_size=page_size
    )

@router.get("/light")
async def get_light_roles(
    search: Optional[str] = None,
    organisation_id: Optional[List[str]] = Query(None),
    client_id: Optional[List[str]] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    permission: bool = Depends(Permission("role_module", "READ"))
):
    """
    Get lightweight roles list for dropdowns/filters.
    """
    return RoleService.get_light_roles(search, db, current_user, organisation_id, client_id)

@router.get("", response_model=RoleListResponse)
@router.get("/", response_model=RoleListResponse)
async def get_roles(
    page: int = 1,
    page_size: int = 10,
    status_id: Optional[str] = None,
    search: Optional[str] = None,
    organisation_id: Optional[List[str]] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    permission: bool = Depends(Permission("role_module", "READ"))
):
    roles, total = RoleService.get_roles(page, page_size, status_id, db, current_user, search, organisation_id)
    return RoleListResponse(
        roles=[RoleResponse(**role) for role in roles],
        total=total,
        page=page,
        page_size=page_size
    )

@router.get("/stats")
async def get_role_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    permission: bool = Depends(Permission("role_module", "READ"))
):
    return RoleService.get_role_stats(db,current_user)

@router.get("/{role_id}", response_model=RoleResponse)
async def get_role(
    role_id: str, 
    db: Session = Depends(get_db),
    permission: bool = Depends(Permission("role_module", "READ"))
):
    role = RoleService.get_role_by_id(role_id, db)
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    return RoleResponse(**role)

@router.get("/{role_id}/modules")
async def get_role_modules(
    role_id: str, 
    db: Session = Depends(get_db),
    permission: bool = Depends(Permission("role_module", "READ"))
):
    modules = RoleService.get_role_modules(role_id, db)
    return {"modules": modules}

@router.get("/{role_id}/users", response_model=UserListResponse)
async def get_role_users(
    role_id: str,
    page: int = 1,
    page_size: int = 10,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
    permission: bool = Depends(Permission("role_module", "READ"))
):
    users, total = RoleService.get_users_mapped_to_role(role_id, page, page_size, search, db)
    return UserListResponse(
        items=[RoleUserResponse(**user) for user in users],
        total=total,
        page=page,
        page_size=page_size
    )

@router.post("", response_model=RoleResponse)
@router.post("/", response_model=RoleResponse)
async def create_role(
    role: RoleCreate, 
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    permission: bool = Depends(Permission("role_module", "CREATE")),
    current_user: User = Depends(get_current_user)
):
    role_data = role.model_dump()

    try:
        created_role = RoleService.create_role(role_data, db, current_user)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    ActivityService.log(
        db=db,
        action="CREATE",
        entity_type="role",
        entity_id=str(created_role["id"]),
        user_id=current_user.id,
        details={"name": created_role["name"]},
        request=request,
        background_tasks=background_tasks
    )

    return RoleResponse(**created_role)


@router.put("/{role_id}", response_model=RoleResponse)
async def update_role(
    role_id: str, 
    role: RoleUpdate, 
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    permission: bool = Depends(Permission("role_module", "UPDATE")),
    current_user: User = Depends(get_current_user)
):
    existing_role = RoleService.get_role_by_id(role_id, db)
    if not existing_role:
        raise HTTPException(status_code=404, detail="Role not found")

    role_data = role.model_dump(exclude_unset=True)

    # ONLY run duplicate check if name is being updated AND changed
    # if "name" in role_data and role_data["name"]:
    #     new_name = role_data["name"].upper()

    #     if new_name != existing_role["name"]:
    #         if RoleService.check_role_name_exists(new_name, role_id, db):
    #             raise HTTPException(
    #                 status_code=400,
    #                 detail="Role with this name already exists"
    #             )
    
    role_data = role.model_dump(exclude_unset=True)
    
    # Calculate changes BEFORE update
    changes = {}
    existing_role = RoleService.get_role_by_id(role_id, db)
    if existing_role:
        # Normalize status_id to statusCode for readable logs
        if 'status_id' in role_data and existing_role.get('statusCode'):
            existing_role['status_id'] = existing_role['statusCode']
            
        changes = ActivityService.calculate_changes(existing_role, role_data) or {}
        modules_changed = 'modules' in role_data

        # allow status-only updates
        if not changes and not modules_changed and 'status_id' not in role_data:
            raise HTTPException(
                status_code=400,
                detail="No changes provided for update"
            )


        # Rename status_id to Status
        if 'status_id' in changes:
            changes['Status'] = changes.pop('status_id')
        if modules_changed:
            changes['Permissions'] = 'Updated'
    try:
        updated_role = RoleService.update_role(role_id, role_data, db, current_user)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not updated_role:
        raise HTTPException(status_code=404, detail="Role not found")
        
    ActivityService.log(
        db=db,
        action="UPDATE",
        entity_type="role",
        entity_id=role_id,
        user_id=current_user.id,
        details={
            "name": updated_role["name"],
            "changes": changes
        },
        request=request,
        background_tasks=background_tasks
    )
        
    return RoleResponse(**updated_role)


@router.delete("/{role_id}")
async def delete_role(
    role_id: str, 
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    permission: bool = Depends(Permission("role_module", "DELETE")),
    current_user: User = Depends(get_current_user)
):
    """Delete a role"""
    name, error = RoleService.delete_role(role_id, db)
    if error:
        raise HTTPException(status_code=400, detail=error)
        
    ActivityService.log(
        db=db,
        action="DELETE",
        entity_type="role",
        entity_id=role_id,
        user_id=current_user.id,
        details={"name": name},
        request=request,
        background_tasks=background_tasks
    )
        
    return {"message": "Role deleted successfully"}
