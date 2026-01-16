from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.orm import Session
from typing import List
from pydantic import BaseModel

from app.core.database import get_db
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
async def get_all_modules(db: Session = Depends(get_db)):
    modules = ModuleService.get_all_modules(db)
    return ModulesResponse(modules=modules)

@router.get("/user-modules", response_model=ModulesResponse)
@router.get("/user-modules/", response_model=ModulesResponse)
async def get_current_user_modules(
    email: str = Query(..., description="User email"),
    db: Session = Depends(get_db)
):
    modules = ModuleService.get_user_modules(email, db)
    if not modules:
        raise HTTPException(status_code=404, detail="User not found")
    return ModulesResponse(modules=modules)