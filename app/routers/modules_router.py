from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.orm import Session
from typing import List
from pydantic import BaseModel

from app.core.database import get_db
from app.core.security import get_current_user, get_current_role_id
from app.models.user import User
from app.services.module_service import ModuleService

router = APIRouter()

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

    class Config:
        from_attributes = True

class ModulesResponse(BaseModel):
    modules: List[ModuleResponse]

@router.get("", response_model=ModulesResponse)
@router.get("/", response_model=ModulesResponse)
async def get_all_modules(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    modules = ModuleService.get_all_modules(db)
    return ModulesResponse(modules=modules)

@router.get("/user-modules", response_model=ModulesResponse)
@router.get("/user-modules/", response_model=ModulesResponse)
async def get_current_user_modules(
    email: str = Query(..., description="User email"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    role_id: str = Depends(get_current_role_id)
):
    modules = ModuleService.get_user_modules(email, db, role_id)
    if not modules:
        # It's possible to have no modules for a role, but if user not found logic remains
        # Actually ModuleService returns [] if user not found OR no modules. 
        # But we should only 404 if user truly doesn't exist? 
        # Service logic: check user existence first.
        pass
    
    # We might want to check if modules is empty and if that's expected. 
    # For now, just return what service returns.
    return ModulesResponse(modules=modules)