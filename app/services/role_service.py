
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


class RoleService:
    
    @staticmethod
    def get_roles(page: int, page_size: int, status_id: Optional[str], db: Session, current_user):
        skip = (page - 1) * page_size

        # print("all roles:", db.query(Role).count())
        # print("non default:", db.query(Role).filter(Role.is_default == False).count())

        query = RoleService._base_roles_query(db)

        # 🔥 ALWAYS hide default roles
        query = query.filter(Role.is_default == False)

        # SUPER ADMIN → sees everything
        if current_user.is_superuser:
            pass

        # CLIENT USER → roles they created
        # elif getattr(current_user, "is_client", False):
        #     query = query.filter(Role.created_by == str(current_user.id))

        # # ORG USER → if org exists filter, else DON'T
        # elif getattr(current_user, "organisation_id", None):
        #     query = query.filter(
        #         or_(
        #             Role.organisation_id == str(current_user.id),
        #             Role.organisation_id.is_(None)
        #         )
        #     )

        if not current_user.is_superuser:
            if getattr(current_user, 'is_client', False):
                query = query.filter(
                    (Role.created_by == str(current_user.id)) |
                    (Role.organisation_id.is_(None) & Role.created_by.is_(None)) # Allow Generic Roles?
                )
            elif current_user.organisation_id:
                 # Organisation Admin: See Own Org Roles + Global System Roles
                 query = query.filter(
                        or_(
                            Role.organisation_id == str(current_user.organisation_id),
                            (Role.organisation_id.is_(None) & Role.created_by.is_(None))
                        )
                    )

        # USER WITHOUT ORG → see roles they created + global roles
        else:
            query = query.filter(
                or_(
                    Role.created_by == str(current_user.id),
                    Role.organisation_id.is_(None)
                )
            )


        if status_id:
            query = query.join(Role.status_relation).filter(Status.code == status_id)

        total = query.count()
        roles = query.offset(skip).limit(page_size).all()


        result = []
        for role in roles:
             # Fetch Created By Name
            created_by_name = None
            created_by_id = getattr(role, 'created_by', None)
            if created_by_id:
                creator = db.query(User).filter(User.id == created_by_id).first()
                if creator:
                   created_by_name = f"{creator.first_name or ''} {creator.last_name or ''}".strip()
                   if not created_by_name:
                       created_by_name = creator.username

            # Fetch Organisation Name
            organisation_name = None
            org_id = getattr(role, 'organisation_id', None)
            if org_id:
                 org = db.query(Organisation).filter(Organisation.id == org_id).first()
                 if org:
                     # Organisation doesn't have business_name, using first/last or username
                     organisation_name = f"{org.name}".strip()
                     if not organisation_name:
                         organisation_name = org.username
            
            users_count = db.query(UserRole).filter(UserRole.role_id == role.id).count()
            result.append({
                "id": role.id,
                "name": role.name,
                # "created_by":role.created_by,
                "created_by_name": created_by_name,
                "organisation_name": organisation_name,
                "description": role.description,
                "status_id": role.status_id,
                "statusCode": role.status_relation.code if role.status_relation else None,
                "can_edit": role.can_edit,
                "users_count": users_count
            })
            
        return result, total

    @staticmethod
    def _base_roles_query(db: Session):
        return (
            db.query(Role)
            .filter(func.upper(Role.name) != 'SUPER_ADMIN')
        )

    @staticmethod
    def get_assignable_roles(page: int, page_size: int, db: Session, current_user):
        skip = (page - 1) * page_size

        query = RoleService._base_roles_query(db)

        # 🔥 ALWAYS hide default roles
        query = query.filter(Role.is_default == False)

        if not current_user.is_superuser:
            if getattr(current_user, 'is_client', False):
                query = query.filter(
                    (User.created_by == str(current_user.id)) |
                    (User.id == str(current_user.id))
                )
            else:
                 query = query.filter(
                        User.organisation_id == str(current_user.id)
                    )

        # USER WITHOUT ORG → see roles they created + global roles
        else:
            query = query.filter(
                or_(
                    Role.created_by == str(current_user.id),
                    Role.organisation_id.is_(None)
                )
            )



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
                "users_count": users_count,
                "organisation_id": str(role.organisation_id) if role.organisation_id else None
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
    def create_role(role_data: Dict, db: Session, current_user) -> Dict:
        active_status = db.query(Status).filter(Status.code == 'ACTIVE').first()
        
        organisation_id_val = None
        created_by_val = None

        if isinstance(current_user, Organisation):
            created_by_val = None
            organisation_id_val = str(current_user.id)
        elif isinstance(current_user, User):
            if not current_user.is_superuser:
                created_by_val = str(current_user.id)
                if current_user.organisation_id:
                    organisation_id_val = str(current_user.organisation_id)
            else:
                created_by_val = None
        
        # Check for duplicate role name within scope
        if RoleService._check_duplicate_role(role_data['name'], db, current_user):
            raise ValueError(f"Role with name '{role_data['name']}' already exists")

        new_role = Role(
            id=str(uuid.uuid4()),
            name=role_data['name'].upper(),
            description=role_data.get('description'),
            status_id=active_status.id if active_status else None,
            created_by=created_by_val,
            organisation_id=organisation_id_val
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
            "created_by":new_role.created_by,
            "description": new_role.description,
            "status_id": new_role.status_id,
            "statusCode": status_code,
            "can_edit": new_role.can_edit,
            "users_count": 0
        }

    @staticmethod
    def update_role(role_id: str, role_data: Dict, db: Session, current_user) -> Optional[Dict]:
        role = db.query(Role).filter(Role.id == role_id).first()
        if not role:
            return None

        # 1. Scope Permission Check
        if isinstance(current_user, Organisation):
            if str(role.organisation_id) != str(current_user.id):
                 # Assuming returning None or raising specific error? Service usually returns None or raises.
                 # Given request context, let's treat as 'Not Found' or invalid.
                 return None 
        elif isinstance(current_user, User) and not current_user.is_superuser:
            if getattr(current_user, 'is_client', False):
                 if str(role.created_by) != str(current_user.id):
                      return None
            elif current_user.organisation_id:
                 if str(role.organisation_id) != str(current_user.organisation_id):
                      return None
            else:
                 # Independent user updating their own role?
                 if str(role.created_by) != str(current_user.id):
                      return None

        if 'name' in role_data and role_data['name'] is not None:
            new_name = role_data['name'].upper()
            if new_name != role.name:
                # 2. Check for duplicates in the same scope
                query = db.query(Role).filter(func.upper(Role.name) == new_name)
                query = query.filter(Role.id != role_id)
                
                if role.organisation_id:
                     query = query.filter(Role.organisation_id == str(role.organisation_id))
                elif role.created_by:
                     query = query.filter(Role.created_by == str(role.created_by))
                     query = query.filter(Role.organisation_id.is_(None))
                else:
                     # Super Admin Scope (Global)
                     query = query.filter(Role.created_by.is_(None), Role.organisation_id.is_(None))
                
                if query.first():
                    raise ValueError(f"Role with name '{role_data['name']}' already exists")

            role.name = new_name

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
    def is_client_user(user):
        return isinstance(user, User) and getattr(user, "is_client", False)

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

        query = db.query(Role).filter(func.upper(Role.name) != "SUPER_ADMIN")
        query = RoleService._base_roles_query(db)

        # 🔥 ALWAYS hide default roles
        query = query.filter(Role.is_default == False)

        # SUPER ADMIN → sees everything
        if current_user.is_superuser:
            pass

        # CLIENT USER → roles they created
        elif getattr(current_user, "is_client", False):
            query = query.filter(Role.created_by == str(current_user.id))

        # ORG USER → if org exists filter, else DON'T
        elif getattr(current_user, "organisation_id", None):
            query = query.filter(
                or_(
                    Role.organisation_id == str(current_user.organisation_id),
                    (Role.organisation_id.is_(None) & Role.created_by.is_(None))
                )
            )

        # USER WITHOUT ORG → see roles they created + global roles
        else:
            query = query.filter(
                or_(
                    Role.created_by == str(current_user.id),
                    (Role.organisation_id.is_(None) & Role.created_by.is_(None))
                )
            )


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
    def check_role_name_exists(name: str, exclude_id: Optional[str], db: Session) -> bool:
        query = db.query(Role).filter(func.upper(Role.name) == name.upper())
        if exclude_id:
            query = query.filter(Role.id != exclude_id)
        return query.first() is not None

    @staticmethod
    def _check_duplicate_role(name: str, db: Session, current_user, exclude_role_id: Optional[str] = None) -> bool:
        query = db.query(Role).filter(func.upper(Role.name) == name.upper())

        if exclude_role_id:
            query = query.filter(Role.id != exclude_role_id)

        if isinstance(current_user, Organisation):
            # Organisation Scope
            query = query.filter(Role.organisation_id == str(current_user.id))
        
        elif isinstance(current_user, User):
            if current_user.is_superuser:
                # Super Admin Scope: created_by IS NULL AND organisation_id IS NULL
                query = query.filter(Role.created_by.is_(None), Role.organisation_id.is_(None))
            
            elif getattr(current_user, 'is_client', False):
                # Client Scope: created_by == current_user.id
                query = query.filter(Role.created_by == str(current_user.id))

            elif current_user.organisation_id:
                 # Organisation User Scope: Check within organisation
                 query = query.filter(Role.organisation_id == str(current_user.organisation_id))
            
            else:
                 # Independent user?
                 query = query.filter(Role.created_by == str(current_user.id))

        return query.first() is not None

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
