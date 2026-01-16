from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.orm import Session
from typing import List
from pydantic import BaseModel

from app.core.database import get_db
from app.models.user import User
from app.models.role import Role
from app.models.module import Module
from app.models.privilege import Privilege
from app.models.role_module import RoleModule
from app.models.user_role import UserRole

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

@router.get("/user-modules", response_model=ModulesResponse)
async def get_current_user_modules(
    email: str = Query(..., description="User email"),
    db: Session = Depends(get_db)
):
    # Get user
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Get user's accessible modules with privileges
    query = db.query(
        Module.id,
        Module.name,
        Module.label,
        Module.description,
        Module.route,
        Module.icon,
        Module.category,
        Module.display_order,
        Module.color_from,
        Module.color_to,
        Privilege.name.label('privilege_name')
    ).join(
        RoleModule, Module.id == RoleModule.module_id
    ).join(
        UserRole, RoleModule.role_id == UserRole.role_id
    ).join(
        Privilege, RoleModule.privilege_id == Privilege.id
    ).filter(
        UserRole.user_id == user.id
    ).order_by(Module.display_order)
    
    results = query.all()
    
    # Group modules with their privileges
    modules_dict = {}
    for result in results:
        module_id = result.id
        if module_id not in modules_dict:
            modules_dict[module_id] = {
                'id': result.id,
                'name': result.name,
                'label': result.label,
                'description': result.description,
                'route': result.route,
                'icon': result.icon,
                'category': result.category,
                'display_order': result.display_order,
                'color_from': result.color_from,
                'color_to': result.color_to,
                'privileges': []
            }
        modules_dict[module_id]['privileges'].append(result.privilege_name)
    
    # Convert to list and sort by display_order
    modules_list = list(modules_dict.values())
    modules_list.sort(key=lambda x: x['display_order'])
    
    return ModulesResponse(modules=modules_list)