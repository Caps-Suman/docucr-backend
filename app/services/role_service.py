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
    def get_roles(page: int, page_size: int, status_id: Optional[str], db: Session) -> Tuple[List[Dict], int]:
        skip = (page - 1) * page_size
        query = db.query(Role)
        
        if status_id:
            query = query.join(Role.status_relation).filter(Status.code == status_id)
            
        total = query.count()
        roles = query.offset(skip).limit(page_size).all()
        
        result = []
        for role in roles:
            users_count = db.query(UserRole).filter(UserRole.role_id == role.id).count()
            # Resolve Status Code
            status_code = role.status_relation.code if role.status_relation else None
                
            result.append({
                "id": role.id,
                "name": role.name,
                "description": role.description,
                "status_id": role.status_id,
                "statusCode": status_code,
                "can_edit": role.can_edit,
                "users_count": users_count
            })
        
        return result, total

    @staticmethod
    def get_assignable_roles(page: int, page_size: int, db: Session) -> Tuple[List[Dict], int]:
        skip = (page - 1) * page_size
        query = db.query(Role).filter(func.upper(Role.name) != 'SUPER_ADMIN')
        total = query.count()
        roles = query.offset(skip).limit(page_size).all()
        
        result = []
        for role in roles:
            users_count = db.query(UserRole).filter(UserRole.role_id == role.id).count()
            status_code = role.status_relation.code if role.status_relation else None
            
            result.append({
                "id": role.id,
                "name": role.name,
                "description": role.description,
                "status_id": role.status_id,
                "statusCode": status_code,
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
        status_code = role.status_relation.code if role.status_relation else None

        return {
            "id": role.id,
            "name": role.name,
            "description": role.description,
            "status_id": role.status_id,
            "statusCode": status_code,
            "can_edit": role.can_edit,
            "users_count": users_count
        }

    @staticmethod
    def get_role_modules(role_id: str, db: Session) -> List[Dict]:
        role_modules = db.query(RoleModule).filter(RoleModule.role_id == role_id).all()
        return [{"module_id": rm.module_id, "privilege_id": rm.privilege_id} for rm in role_modules]

    @staticmethod
    def create_role(role_data: Dict, db: Session) -> Dict:
        active_status = db.query(Status).filter(Status.code == 'ACTIVE').first()
        
        new_role = Role(
            id=str(uuid.uuid4()),
            name=role_data['name'].upper(),
            description=role_data.get('description'),
            status_id=active_status.id if active_status else None
        )
        
        db.add(new_role)
        db.commit()
        db.refresh(new_role)
        
        if role_data.get('modules'):
            RoleService._assign_modules(new_role.id, role_data['modules'], db)
        
        status_code = new_role.status_relation.code if new_role.status_relation else (active_status.code if active_status else None)
        
        return {
            "id": new_role.id,
            "name": new_role.name,
            "description": new_role.description,
            "status_id": new_role.status_id,
            "statusCode": status_code,
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
            # If status_id is string Code, resolve to ID
            status_code = role_data['status_id']
            # Find status by code, try both exact and upper/lower to be safe? No, just match code standard
            # But the user might send lowercase? I should probably .upper() existing input just in case
            # But let's stick to using code==status_code check.
            status = db.query(Status).filter(Status.code == status_code).first()
            if status:
                role.status_id = status.id
        
        if 'modules' in role_data and role_data['modules'] is not None:
            role_module_ids = [rm.id for rm in db.query(RoleModule).filter(RoleModule.role_id == role_id).all()]
            if role_module_ids:
                db.query(UserRoleModule).filter(UserRoleModule.role_module_id.in_(role_module_ids)).delete(synchronize_session=False)
            db.query(RoleModule).filter(RoleModule.role_id == role_id).delete(synchronize_session=False)
            RoleService._assign_modules(role_id, role_data['modules'], db)
        
        db.commit()
        db.refresh(role)
        
        users_count = db.query(UserRole).filter(UserRole.role_id == role.id).count()
        status_code = role.status_relation.code if role.status_relation else None
        
        return {
            "id": role.id,
            "name": role.name,
            "description": role.description,
            "status_id": role.status_id,
            "statusCode": status_code,
            "can_edit": role.can_edit,
            "users_count": users_count
        }

    @staticmethod
    def delete_role(role_id: str, db: Session) -> Tuple[Optional[str], Optional[str]]:
        role = db.query(Role).filter(Role.id == role_id).first()
        if not role:
            return None, "Role not found"
        
        users_count = db.query(UserRole).filter(UserRole.role_id == role_id).count()
        if users_count > 0:
            return None, f"Cannot delete role with {users_count} assigned users"
        
        role_name = role.name
        db.delete(role)
        db.commit()
        return role_name, None
    
    @staticmethod
    def get_role_stats(db: Session) -> Dict:
        total_roles = db.query(func.count(Role.id)).scalar()
        active_status = db.query(Status).filter(Status.code == 'ACTIVE').first()
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
