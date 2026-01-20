from sqlalchemy.orm import Session
from typing import List, Dict

from app.models.user import User
from app.models.module import Module
from app.models.privilege import Privilege
from app.models.role_module import RoleModule
from app.models.user_role import UserRole


class ModuleService:
    @staticmethod
    def get_all_modules(db: Session) -> List[Dict]:
        modules = db.query(Module).filter(Module.is_active == True).order_by(Module.display_order).all()
        
        return [{
            'id': m.id,
            'name': m.name,
            'label': m.label,
            'description': m.description or '',
            'route': m.route,
            'icon': m.icon or '',
            'category': m.category,
            'display_order': m.display_order,
            'color_from': m.color_from or '',
            'color_to': m.color_to or '',
            'privileges': []
        } for m in modules]

    @staticmethod
    def get_user_modules(email: str, db: Session, role_id: str = None) -> List[Dict]:
        user = db.query(User).filter(User.email == email).first()
        if not user:
            return []
        
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
        )

        if role_id:
            query = query.filter(RoleModule.role_id == role_id)

        query = query.order_by(Module.display_order)
        
        results = query.all()
        
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
        
        modules_list = list(modules_dict.values())
        modules_list.sort(key=lambda x: x['display_order'])
        
        return modules_list
