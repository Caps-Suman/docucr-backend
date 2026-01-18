from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List

from app.core.database import get_db
from app.core.security import get_current_user
from app.services.role_service import RoleService

router = APIRouter(dependencies=[Depends(get_current_user)])

class ModulePermission(BaseModel):
    module_id: str
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

    class Config:
        from_attributes = True

class RoleListResponse(BaseModel):
    roles: List[RoleResponse]
    total: int
    page: int
    page_size: int

@router.get("/assignable", response_model=RoleListResponse)
async def get_assignable_roles(
    page: int = 1,
    page_size: int = 10,
    db: Session = Depends(get_db)
):
    roles, total = RoleService.get_assignable_roles(page, page_size, db)
    return RoleListResponse(
        roles=[RoleResponse(**role) for role in roles],
        total=total,
        page=page,
        page_size=page_size
    )

@router.get("", response_model=RoleListResponse)
@router.get("/", response_model=RoleListResponse)
async def get_roles(
    page: int = 1,
    page_size: int = 10,
    status_id: Optional[str] = None,
    db: Session = Depends(get_db)
):
    roles, total = RoleService.get_roles(page, page_size, status_id, db)
    return RoleListResponse(
        roles=[RoleResponse(**role) for role in roles],
        total=total,
        page=page,
        page_size=page_size
    )

@router.get("/stats")
async def get_role_stats(db: Session = Depends(get_db)):
    return RoleService.get_role_stats(db)

@router.get("/{role_id}", response_model=RoleResponse)
async def get_role(role_id: str, db: Session = Depends(get_db)):
    role = RoleService.get_role_by_id(role_id, db)
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    return RoleResponse(**role)

@router.get("/{role_id}/modules")
async def get_role_modules(role_id: str, db: Session = Depends(get_db)):
    modules = RoleService.get_role_modules(role_id, db)
    return {"modules": modules}

@router.post("", response_model=RoleResponse)
@router.post("/", response_model=RoleResponse)
async def create_role(role: RoleCreate, db: Session = Depends(get_db)):
    if RoleService.check_role_name_exists(role.name, None, db):
        raise HTTPException(status_code=400, detail="Role with this name already exists")
    
    role_data = role.model_dump()
    created_role = RoleService.create_role(role_data, db)
    return RoleResponse(**created_role)

@router.put("/{role_id}", response_model=RoleResponse)
async def update_role(role_id: str, role: RoleUpdate, db: Session = Depends(get_db)):
    if role.name and RoleService.check_role_name_exists(role.name, role_id, db):
        raise HTTPException(status_code=400, detail="Role with this name already exists")
    
    role_data = role.model_dump(exclude_unset=True)
    updated_role = RoleService.update_role(role_id, role_data, db)
    if not updated_role:
        raise HTTPException(status_code=404, detail="Role not found")
    return RoleResponse(**updated_role)

@router.delete("/{role_id}")
async def delete_role(role_id: str, db: Session = Depends(get_db)):
    success, error = RoleService.delete_role(role_id, db)
    if not success:
        raise HTTPException(status_code=400, detail=error)
    return {"message": "Role deleted successfully"}
