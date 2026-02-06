from sqlalchemy.orm import Session
from sqlalchemy import func, or_
from typing import Optional, List, Dict, Tuple
import uuid

from app.models.role import Role
from app.models.user import User
from app.models.organisation import Organisation
from app.models.organisation_role import OrganisationRole
from app.models.user_role import UserRole
from app.models.role_module import RoleModule
from app.models.role_submodule import RoleSubmodule
from app.models.user_role_module import UserRoleModule
from app.models.status import Status
from app.services.user_service import UserService


def is_superadmin(user):
    return isinstance(user, User) and user.is_superuser

def is_client_user(user):
    return isinstance(user, User) and getattr(user, "is_client", False)

def is_org_user(user):
    return (
        isinstance(user, User)
        and not user.is_superuser
        and not getattr(user, "is_client", False)
        and user.organisation_id is not None
    )

def is_org_object(user):
    return isinstance(user, Organisation)

class RoleService:
    
    @staticmethod
    def get_roles(page, page_size, status_id, db, current_user):
        skip = (page - 1) * page_size

        if isinstance(current_user, Organisation):
            org_id = str(current_user.id)
        elif isinstance(current_user, User):
            if current_user.is_superuser:
                org_id = None
            else:
                org_id = str(current_user.organisation_id)
        else:
            org_id = None

        query = (
            db.query(Role, User)
            .outerjoin(User, User.id == Role.created_by)
            .filter(func.upper(Role.name) != "SUPER_ADMIN")
        )

        if org_id:
            query = query.filter(Role.organisation_id == org_id)

        if status_id:
            query = query.join(Role.status_relation).filter(Status.code == status_id)

        total = query.count()
        rows = query.offset(skip).limit(page_size).all()

        result = []
        for role, creator in rows:
            users_count = db.query(UserRole).filter(UserRole.role_id == role.id).count()

            creator_name = None
            if creator:
                creator_name = f"{creator.first_name} {creator.last_name}".strip()

            result.append({
                "id": role.id,
                "name": role.name,
                "description": role.description,
                "status_id": role.status_id,
                "statusCode": role.status_relation.code if role.status_relation else None,
                "can_edit": role.can_edit,
                "users_count": users_count,
                "created_by": creator_name
            })

        return result, total

    @staticmethod
    def _base_roles_query(db: Session):
        return (
            db.query(Role)
            .filter(func.upper(Role.name) != 'SUPER_ADMIN')
        )

    @staticmethod
    def get_assignable_roles(page, page_size, db, current_user):
        skip = (page - 1) * page_size

        # resolve org
        if isinstance(current_user, Organisation):
            org_id = str(current_user.id)
        elif isinstance(current_user, User):
            if current_user.is_superuser:
                org_id = None
            else:
                org_id = str(current_user.organisation_id)
        else:
            org_id = None

        query = db.query(Role).filter(func.upper(Role.name) != "SUPER_ADMIN")

        if org_id:
            query = query.filter(Role.organisation_id == org_id)

        total = query.count()
        roles = query.offset(skip).limit(page_size).all()

        result = []
        for role in roles:
            users_count = db.query(UserRole).filter(UserRole.role_id == role.id).count()

            result.append({
                "id": role.id,
                "name": role.name,
                "description": role.description,
                "status_id": role.status_id,
                "statusCode": role.status_relation.code if role.status_relation else None,
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
    def get_users_mapped_to_role(
        role_id: str,
        page: int,
        page_size: int,
        search: Optional[str],
        db: Session
    ) -> Tuple[List[Dict], int]:
        from app.models.user import User
        # Check if role exists
        role = db.query(Role).filter(Role.id == role_id).first()
        if not role:
            return [], 0

        # Query users mapped to this role
        query = db.query(User).join(User.roles).filter(Role.id == role_id)

        # Apply search filter
        if search:
            search_term = f"%{search}%"
            query = query.filter(
                (User.first_name.ilike(search_term)) |
                (User.last_name.ilike(search_term)) |
                (User.email.ilike(search_term)) |
                (User.phone_number.ilike(search_term))
            )

        # Count total before pagination
        total = query.count()

        # Apply pagination
        offset = (page - 1) * page_size
        users = query.offset(offset).limit(page_size).all()

        # Format result
        user_list = []
        for user in users:
            name_parts = [p for p in [user.first_name, user.middle_name, user.last_name] if p]
            full_name = " ".join(name_parts)
            
            user_list.append({
                "id": str(user.id),
                "name": full_name,
                "email": user.email,
                "phone": user.phone_number
            })

        return user_list, total

    @staticmethod
    def get_role_modules(role_id: str, db: Session) -> List[Dict]:
        role_modules = db.query(RoleModule).filter(RoleModule.role_id == role_id).all()
        role_submodules = db.query(RoleSubmodule).filter(RoleSubmodule.role_id == role_id).all()
        
        result = [{"module_id": rm.module_id, "privilege_id": rm.privilege_id} for rm in role_modules]
        result.extend([{"module_id": None, "submodule_id": rs.submodule_id, "privilege_id": rs.privilege_id} for rs in role_submodules])
        return result

    @staticmethod
    def create_role(role_data, db, current_user):
        name = role_data["name"].strip().upper()

        # resolve org
        if isinstance(current_user, Organisation):
            org_id = str(current_user.id)
            creator_id = None
        else:
            org_id = str(current_user.organisation_id)
            creator_id = str(current_user.id)

        if not org_id:
            raise ValueError("Organisation not found")

        # duplicate check inside this org
        exists = db.query(Role).filter(
            func.upper(Role.name) == name,
            Role.organisation_id == org_id
        ).first()

        if exists:
            raise ValueError("Role already exists for this organisation")

        new_role = Role(
            id=str(uuid.uuid4()),
            name=name,
            description=role_data.get("description"),
            organisation_id=org_id,
            created_by=creator_id
        )

        db.add(new_role)
        db.commit()
        db.refresh(new_role)

        return {
            "id": new_role.id,
            "name": new_role.name,
            "description": new_role.description,
            "status_id": new_role.status_id,
            "statusCode": new_role.status_relation.code if new_role.status_relation else None,
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
        if 'status_id' in role_data and role_data['status_id'] is not None:
            value = role_data['status_id']

            # if string like "ACTIVE"
            if isinstance(value, str) and not value.isdigit():
                status = db.query(Status).filter(Status.code == value.upper()).first()
                if status:
                    role.status_id = status.id
            else:
                # numeric id
                role.status_id = value

        if 'modules' in role_data and role_data['modules'] is not None:
            role_module_ids = [rm.id for rm in db.query(RoleModule).filter(RoleModule.role_id == role_id).all()]
            if role_module_ids:
                db.query(UserRoleModule).filter(UserRoleModule.role_module_id.in_(role_module_ids)).delete(synchronize_session=False)
            db.query(RoleModule).filter(RoleModule.role_id == role_id).delete(synchronize_session=False)
            db.query(RoleSubmodule).filter(RoleSubmodule.role_id == role_id).delete(synchronize_session=False)
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
    def get_role_stats(db, current_user):

        org_id = UserService.resolve_org_id(current_user)

        query = db.query(Role).filter(func.upper(Role.name) != "SUPER_ADMIN")

        if org_id:
            query = query.filter(Role.organisation_id == org_id)

        total = query.count()

        active = (
            query.join(Role.status_relation)
            .filter(Status.code == "ACTIVE")
            .count()
        )

        return {
            "total_roles": total,
            "active_roles": active,
            "inactive_roles": total - active
        }


    @staticmethod
    def check_role_name_exists(name, exclude_id, db, current_user):
        name = name.upper()

        if isinstance(current_user, Organisation):
            org_id = str(current_user.id)
        else:
            org_id = str(current_user.organisation_id)

        query = db.query(Role).filter(
            func.upper(Role.name) == name,
            Role.organisation_id == org_id
        )

        if exclude_id:
            query = query.filter(Role.id != exclude_id)

        return db.query(query.exists()).scalar()


    @staticmethod
    def _assign_modules(role_id: str, modules: List[Dict], db: Session):
        for module_perm in modules:
            if module_perm.get('privilege_id'):
                if module_perm.get('submodule_id'):
                    role_submodule = RoleSubmodule(
                        id=str(uuid.uuid4()),
                        role_id=role_id,
                        submodule_id=module_perm['submodule_id'],
                        privilege_id=module_perm['privilege_id']
                    )
                    db.add(role_submodule)
                elif module_perm.get('module_id'):
                    role_module = RoleModule(
                        id=str(uuid.uuid4()),
                        role_id=role_id,
                        module_id=module_perm['module_id'],
                        privilege_id=module_perm['privilege_id']
                    )
                    db.add(role_module)
        db.commit()
