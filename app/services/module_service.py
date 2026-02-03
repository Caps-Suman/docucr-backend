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
        # Fetch all privileges to assign to each module/submodule as available options
        # Note: In a more complex system, this might be restricted per module, but for now we expose all system privileges.
        all_privileges = [p.name for p in db.query(Privilege).all()]
        
        
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
            'privileges': all_privileges,
            'submodules': [{
                'id': s.id,
                'name': s.name,
                'label': s.label,
                'route_key': s.route_key,
                'display_order': s.display_order,
                'privileges': all_privileges
            } for s in m.submodules_list]
        } for m in modules]

    @staticmethod
    def get_user_modules(email: str, db: Session, role_id: str = None) -> List[Dict]:
        user = db.query(User).filter(User.email == email).first()
        if not user:
            return []
        
        # Query for RoleModule (Module-level permissions)
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

        module_results = query.all()

        # Query for RoleSubmodule (Submodule-level permissions)
        from app.models.role_submodule import RoleSubmodule
        from app.models.submodule import Submodule
        
        sub_query = db.query(
            Module.id.label('module_id'),
            Module.name.label('module_name'),
            Module.label.label('module_label'),
            Module.description.label('module_desc'),
            Module.route.label('module_route'),
            Module.icon.label('module_icon'),
            Module.category.label('module_cat'),
            Module.display_order.label('module_order'),
            Module.color_from.label('module_color_from'),
            Module.color_to.label('module_color_to'),
            Submodule.id.label('submodule_id'),
            Submodule.name.label('submodule_name'),
            Submodule.label.label('submodule_label'),
            Submodule.route_key.label('submodule_route_key'),
            Submodule.display_order.label('submodule_order'),
            Privilege.name.label('privilege_name')
        ).join(
            Submodule, Module.id == Submodule.module_id
        ).join(
            RoleSubmodule, Submodule.id == RoleSubmodule.submodule_id
        ).join(
            UserRole, RoleSubmodule.role_id == UserRole.role_id
        ).join(
            Privilege, RoleSubmodule.privilege_id == Privilege.id
        ).filter(
            UserRole.user_id == user.id
        )

        if role_id:
            sub_query = sub_query.filter(RoleSubmodule.role_id == role_id)

        sub_results = sub_query.all()
        
        modules_dict = {}
        
        # Process Module-Level Permissions
        for result in module_results:
            module_id = result.id
            if module_id not in modules_dict:
                modules_dict[module_id] = {
                    'id': result.id,
                    'name': result.name,
                    'label': result.label,
                    'description': result.description or '',
                    'route': result.route,
                    'icon': result.icon or '',
                    'category': result.category,
                    'display_order': result.display_order or 0,
                    'color_from': result.color_from or '',
                    'color_to': result.color_to or '',
                    'privileges': [],
                    'submodules': [] 
                }
            # Check if privilege is not already in list to avoid duplicates (though usually distinct)
            if result.privilege_name and result.privilege_name not in modules_dict[module_id]['privileges']:
                modules_dict[module_id]['privileges'].append(result.privilege_name)

        # Process Submodule-Level Permissions
        for result in sub_results:
            module_id = result.module_id
            if module_id not in modules_dict:
                 modules_dict[module_id] = {
                    'id': result.module_id,
                    'name': result.module_name,
                    'label': result.module_label,
                    'description': result.module_desc or '',
                    'route': result.module_route,
                    'icon': result.module_icon or '',
                    'category': result.module_cat,
                    'display_order': result.module_order or 0,
                    'color_from': result.module_color_from or '',
                    'color_to': result.module_color_to or '',
                    'privileges': [], # Usually empty if only submodule access
                    'submodules': []
                }
            
            # Find or create submodule entry
            submodule = next((s for s in modules_dict[module_id]['submodules'] if s['id'] == result.submodule_id), None)
            if not submodule:
                submodule = {
                    'id': result.submodule_id,
                    'name': result.submodule_name,
                    'label': result.submodule_label,
                    'route_key': result.submodule_route_key,
                    'display_order': result.submodule_order or 0,
                    'privileges': []
                }
                modules_dict[module_id]['submodules'].append(submodule)
            
            if result.privilege_name and result.privilege_name not in submodule['privileges']:
                submodule['privileges'].append(result.privilege_name)
        
        modules_list = list(modules_dict.values())
        modules_list.sort(key=lambda x: x['display_order'])
        # Sort submodules
        for m in modules_list:
            m['submodules'].sort(key=lambda x: x['display_order'])
            # Also populate 'all' submodules for modules that are fully accessible? 
            # No, standard practice: if you have module level access, do you see all submodules? 
            # Usually yes, or permissions might be strictly additive. 
            # For now, let's assume if module-level access exists, we should probably fetch ALL submodules for that module just for display, 
            # OR we rely on separate submodule permissions. 
            # Let's stick to: If checking user modules, we show what they have explicit access to. 
            # However, if I have 'READ' on 'User Management', I probably want to see the 'Users' tab.
            # But we are moving to granular. 
            # If I have 'READ' on the MODULE, does it imply READ on all submodules? 
            # If so, I should fetch all submodules for that module. 
            # But the current requirement is granular submodule "table for each module".
            # So I will assume strict granular access or mixed.
            pass

        return modules_list
