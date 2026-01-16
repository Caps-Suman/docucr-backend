from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional, List, Dict, Tuple
import uuid

from app.models.role import Role
from app.models.user_role import UserRole
from app.models.role_module import RoleModule
from app.models.user_role_module import UserRoleModule
from app.models.status import Status


class RoleService:
    @staticmethod
    def get_roles(page: int, page_size: int, db: Session) -> Tuple[List[Dict], int]:
        skip = (page - 1) * page_size
        total = db.query(func.count(Role.id)).scalar()
        roles = db.query(Role).offset(skip).limit(page_size).all()
        
        result = []
        for role in roles:
            users_count = db.query(UserRole).filter(UserRole.role_id == role.id).count()
            result.append({
                "id": role.id,
                "name": role.name,
                "description": role.description,
                "status_id": role.status_id,
                "can_edit": role.can_edit,
                "users_count": users_count
            })
        
        return result, total

    @staticmethod
    def get_role_by_id(role_id: str, db: Session) -> Optional[Dict]:
        role = db.query(Role).filter(Role.id == role_id).first()
        if not role:
            return None
        
        users_count = db.query(UserRole).filter(UserRole.role_id == role.id).count()
        return {
            "id": role.id,
            "name": role.name,
            "description": role.description,
            "status_id": role.status_id,
            "can_edit": role.can_edit,
            "users_count": users_count
        }

    @staticmethod
    def get_role_modules(role_id: str, db: Session) -> List[Dict]:
        role_modules = db.query(RoleModule).filter(RoleModule.role_id == role_id).all()
        return [{"module_id": rm.module_id, "privilege_id": rm.privilege_id} for rm in role_modules]

    @staticmethod
    def create_role(role_data: Dict, db: Session) -> Dict:
        active_status = db.query(Status).filter(Status.name == 'ACTIVE').first()
        
        new_role = Role(
            id=str(uuid.uuid4()),
            name=role_data['name'].upper(),
            description=role_data.get('description'),
            status_id=active_status.id
        )
        
        db.add(new_role)
        db.commit()
        db.refresh(new_role)
        
        if role_data.get('modules'):
            RoleService._assign_modules(new_role.id, role_data['modules'], db)
        
        return {
            "id": new_role.id,
            "name": new_role.name,
            "description": new_role.description,
            "status_id": new_role.status_id,
            "can_edit": new_role.can_edit,
            "users_count": 0
        }

    @staticmethod
    def update_role(role_id: str, role_data: Dict, db: Session) -> Optional[Dict]:
        role = db.query(Role).filter(Role.id == role_id).first()
        if not role:
            return None
        
        if 'name' in role_data and role_data['name'] is not None:
            role.name = role_data['name'].upper()
        if 'description' in role_data:
            role.description = role_data['description']
        if 'status_id' in role_data:
            role.status_id = role_data['status_id']
        
        if 'modules' in role_data and role_data['modules'] is not None:
            role_module_ids = [rm.id for rm in db.query(RoleModule).filter(RoleModule.role_id == role_id).all()]
            if role_module_ids:
                db.query(UserRoleModule).filter(UserRoleModule.role_module_id.in_(role_module_ids)).delete(synchronize_session=False)
            db.query(RoleModule).filter(RoleModule.role_id == role_id).delete(synchronize_session=False)
            RoleService._assign_modules(role_id, role_data['modules'], db)
        
        db.commit()
        db.refresh(role)
        
        users_count = db.query(UserRole).filter(UserRole.role_id == role.id).count()
        return {
            "id": role.id,
            "name": role.name,
            "description": role.description,
            "status_id": role.status_id,
            "can_edit": role.can_edit,
            "users_count": users_count
        }

    @staticmethod
    def delete_role(role_id: str, db: Session) -> Tuple[bool, Optional[str]]:
        role = db.query(Role).filter(Role.id == role_id).first()
        if not role:
            return False, "Role not found"
        
        users_count = db.query(UserRole).filter(UserRole.role_id == role_id).count()
        if users_count > 0:
            return False, f"Cannot delete role with {users_count} assigned users"
        
        db.delete(role)
        db.commit()
        return True, None

    @staticmethod
    def get_role_stats(db: Session) -> Dict:
        total_roles = db.query(func.count(Role.id)).scalar()
        active_status = db.query(Status).filter(Status.name == 'ACTIVE').first()
        active_roles = db.query(func.count(Role.id)).filter(Role.status_id == active_status.id).scalar() if active_status else 0
        
        return {
            "total_roles": total_roles,
            "active_roles": active_roles,
            "inactive_roles": total_roles - active_roles
        }

    @staticmethod
    def check_role_name_exists(name: str, exclude_id: Optional[str], db: Session) -> bool:
        query = db.query(Role).filter(func.upper(Role.name) == name.upper())
        if exclude_id:
            query = query.filter(Role.id != exclude_id)
        return query.first() is not None

    @staticmethod
    def _assign_modules(role_id: str, modules: List[Dict], db: Session):
        for module_perm in modules:
            if module_perm.get('privilege_id'):
                role_module = RoleModule(
                    id=str(uuid.uuid4()),
                    role_id=role_id,
                    module_id=module_perm['module_id'],
                    privilege_id=module_perm['privilege_id']
                )
                db.add(role_module)
        db.commit()
