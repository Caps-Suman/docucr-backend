from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.orm import Session
from typing import List
from pydantic import BaseModel

from app.core.database import get_db
from app.core.security import get_current_user, get_current_role_id
from app.core.permissions import Permission
from app.models.user import User
from app.services.module_service import ModuleService

router = APIRouter()

class SubmoduleResponse(BaseModel):
    id: str
    name: str
    label: str
    route_key: str
    display_order: int
    privileges: List[str] = []

    class Config:
        from_attributes = True

class ModuleResponse(BaseModel):
    id: str
    name: str
    label: str
    description: str
    route: str
    icon: str
    category: str
    display_order: int
    color_from: str
    color_to: str
    privileges: List[str]
    submodules: List[SubmoduleResponse] = []

    class Config:
        from_attributes = True

class ModulesResponse(BaseModel):
    modules: List[ModuleResponse]

@router.get("", response_model=ModulesResponse)
@router.get("/", response_model=ModulesResponse)
async def get_all_modules(
    db: Session = Depends(get_db), 
    current_user: User = Depends(get_current_user),
    role_id: str = Depends(get_current_role_id)
):
    if getattr(current_user, 'context_is_superadmin', False) and not getattr(current_user, "context_organisation_id", None):
        modules = ModuleService.get_all_modules(db)
    else:
        modules = ModuleService.get_user_modules(
            current_user.email,
            db,
            role_id,
            getattr(current_user, "context_organisation_id", None)
        )


    return ModulesResponse(modules=modules)

@router.get("/user-modules", response_model=ModulesResponse)
@router.get("/user-modules/", response_model=ModulesResponse)
async def get_current_user_modules(
    email: str = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    role_id: str = Depends(get_current_role_id)
):
    org_id = getattr(current_user, "context_organisation_id", None)

    modules = ModuleService.get_user_modules(
        email=email,
        db=db,
        role_id=role_id,
        organisation_id=org_id
    )

    return ModulesResponse(modules=modules)
