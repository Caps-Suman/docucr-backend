from sqlalchemy.orm import Session
from sqlalchemy import and_, func, or_
from typing import Optional, List, Dict, Tuple
import uuid
from fastapi import HTTPException

from app.models.user import User
from app.models.user_role import UserRole
from app.models.role import Role
from app.models.status import Status
from app.models.user_supervisor import UserSupervisor
from app.models.user_client import UserClient
from app.models.client import Client
from app.models.organisation import Organisation
from app.core.security import get_password_hash


class UserService:
    @staticmethod
    def _base_visible_users_query(db: Session, current_user: User):
        query = db.query(User).filter(
            ~db.query(UserRole)
            .join(Role)
            .filter(
                UserRole.user_id == User.id,
                Role.name == "SUPER_ADMIN"
            )
            .exists()
        )

        role_names = [role.name for role in current_user.roles]

        if current_user.is_superuser or "ADMIN" in role_names or "SUPER_ADMIN" in role_names:
            return query

        if current_user.is_supervisor:
            subordinate_ids = (
                db.query(UserSupervisor.user_id)
                .filter(UserSupervisor.supervisor_id == current_user.id)
            )
            return query.filter(
                (User.id == current_user.id) |
                (User.id.in_(subordinate_ids))
            )

        return query.filter(User.id == current_user.id)

    @staticmethod
    def _get_role_names(user: User) -> List[str]:
        return [role.name for role in user.roles]
    @staticmethod
    def get_users_by_role(role_id: str, db: Session, current_user: User) -> List[Dict]:
        query = (
            db.query(User)
            .join(UserRole, UserRole.user_id == User.id)
            .filter(UserRole.role_id == role_id)
            .filter(
                ~db.query(UserRole)
                .join(Role)
                .filter(
                    UserRole.user_id == User.id,
                    Role.name == "SUPER_ADMIN"
                )
                .exists()
            )
        )

        # Visibility rules
        if not UserService._is_admin(current_user):
            if current_user.is_supervisor:
                subordinate_ids = (
                    db.query(UserSupervisor.user_id)
                    .filter(UserSupervisor.supervisor_id == current_user.id)
                )
                query = query.filter(User.id.in_(subordinate_ids))
            else:
                query = query.filter(False)

        users = query.all()
        return [UserService._format_user_response(u, db) for u in users]

    @staticmethod
    def _is_admin(user: User) -> bool:
        roles = UserService._get_role_names(user)
        return user.is_superuser or "ADMIN" in roles or "SUPER_ADMIN" in roles

    @staticmethod
    def _is_supervisor(user: User) -> bool:
        return user.is_supervisor is True
    @staticmethod
    def _get_context_org(current_user):
        return getattr(current_user, "context_organisation_id", None)
    
    @staticmethod
    def _ctx_org(user):
        return getattr(user, "context_organisation_id", None) or getattr(user, "organisation_id", None)

    @staticmethod
    def _ctx_role(user):
        return getattr(user, "context_role_id", None)

    @staticmethod
    def _ctx_is_super(user):
        return getattr(user, "context_is_superadmin", False)

    @staticmethod
    def get_users(
        page: int, 
        page_size: int, 
        search: Optional[str], 
        status_id: Optional[str], 
        db: Session, 
        current_user: User,
        role_id: Optional[List[str]] = None,
        organisation_id: Optional[List[str]] = None,
        client_id: Optional[List[str]] = None,
        created_by: Optional[List[str]] = None
    ) -> Tuple[List[Dict], int]:
        skip = (page - 1) * page_size
        query = db.query(User)
        
        # Exclude users with SUPER_ADMIN role
        query = query.filter(
            ~db.query(UserRole).join(Role).filter(
                UserRole.user_id == User.id,
                Role.name == 'SUPER_ADMIN'
            ).exists()
        )

        is_super = False
        if isinstance(current_user, User):
            is_super = UserService._ctx_is_super(current_user)

        # Exclude users with ORGANISATION_ADMIN unless the current user is a SUPER_ADMIN
        if not is_super:
            query = query.filter(
                ~db.query(UserRole).join(Role).filter(
                    UserRole.user_id == User.id,
                    Role.name == 'ORGANISATION_ADMIN'
                ).exists()
            )

        # ---------------------------------------------------------
        # Handle ORGANISATION/CLIENT Login (Instance Checks)
        # ---------------------------------------------------------
        if isinstance(current_user, Client):
            query = query.filter(User.client_id == str(current_user.id))

        elif isinstance(current_user, User):
            role_names = [r.name for r in current_user.roles]

            context_org = UserService._ctx_org(current_user)
            is_super = UserService._ctx_is_super(current_user)

            # -----------------------------
            # GLOBAL SUPERADMIN (no org)
            # -----------------------------
            if is_super and not context_org:
                pass

            # -----------------------------
            # SUPERADMIN inside org
            # -----------------------------
            elif is_super and context_org:
                query = query.filter(User.organisation_id == str(context_org))

            # -----------------------------
            # ORG ROLE USER
            # -----------------------------
            elif "ORGANISATION_ADMIN" in role_names:
                if context_org:
                    query = query.filter(User.organisation_id == str(context_org))

            # -----------------------------
            # CLIENT ADMIN
            # -----------------------------
            elif "CLIENT_ADMIN" in role_names or getattr(current_user, "is_client", False):
                filters = []

                if current_user.client_id:
                    filters.append(User.client_id == str(current_user.client_id))

                filters.append(User.created_by == str(current_user.id))
                query = query.filter(or_(*filters))
                query = query.filter(User.id != str(current_user.id))

            # -----------------------------
            # STANDARD USER
            # -----------------------------
            else:
                query = query.filter(User.created_by == str(current_user.id))

        if status_id:
            query = query.join(User.status_relation).filter(Status.code == status_id)

        if client_id:
            # Filter by specific client_id (implicit or explicit link)
            if isinstance(client_id, list):
                query = query.filter(User.client_id.in_(client_id))
            else:
                query = query.filter(User.client_id == client_id)

        if organisation_id:
            if isinstance(organisation_id, list):
                query = query.filter(User.organisation_id.in_(organisation_id))
            else:
                query = query.filter(User.organisation_id == organisation_id)

        if created_by:
            if isinstance(created_by, list):
                query = query.filter(User.created_by.in_(created_by))
            else:
                query = query.filter(User.created_by == created_by)

        if role_id:
            # Handle list or single string (though type hint says List, runtime might vary if not careful, but Router ensures list)
            if isinstance(role_id, list):
                 query = query.join(UserRole).filter(UserRole.role_id.in_(role_id))
            else:
                 query = query.join(UserRole).filter(UserRole.role_id == role_id)

        if search:
            query = query.filter(
                or_(
                    User.email.ilike(f"%{search}%"),
                    User.username.ilike(f"%{search}%"),
                    User.first_name.ilike(f"%{search}%"),
                    User.last_name.ilike(f"%{search}%"),
                    User.phone_number.ilike(f"%{search}%"),
                    # Add full name search
                    func.concat(User.first_name, ' ', User.last_name).ilike(f"%{search}%")
                )
            )
        
        total = query.count()
        # Fix for pagination visibility issue: Default sort by created_at DESC
        query = query.order_by(User.created_at.desc())
        
        users = query.offset(skip).limit(page_size).all()
        
        return [
            UserService._format_user_response(u, db)
            for u in users
        ], total

    @staticmethod
    def get_creators(
        search: Optional[str], 
        db: Session, 
        current_user: User,
        organisation_id: Optional[List[str]] = None,
        client_id: Optional[List[str]] = None
    ) -> List[Dict]:
        """
        Fetch lightweight list of users who are potential creators.
        Filters by search, org, and client, but returns simplified objects.
        """
        query = db.query(User)
        
        if isinstance(current_user, Client):
            # Enforce Client Isolation
            query = query.filter(User.client_id == str(current_user.id))

        elif isinstance(current_user, User):
            role_names = [r.name for r in current_user.roles]

            if current_user.is_superuser or "SUPER_ADMIN" in role_names:
                pass
            
            elif "ORGANISATION_ADMIN" in role_names:
                if current_user.organisation_id:
                    query = query.filter(User.organisation_id == str(current_user.organisation_id))

            elif "CLIENT_ADMIN" in role_names or getattr(current_user, 'is_client', False):
                 filters = []
                 if current_user.client_id:
                     filters.append(User.client_id == str(current_user.client_id))
                 
                 filters.append(User.created_by == str(current_user.id))
                 query = query.filter(or_(*filters))
            
            else:
                 # Standard User -> Only show themselves? (as per "fetch only created user by login user")
                 # This implies they can only filter by themselves
                 query = query.filter(User.id == str(current_user.id))
        
        # Additional Filters
        if organisation_id:
            if isinstance(organisation_id, list):
                query = query.filter(User.organisation_id.in_(organisation_id))
            else:
                query = query.filter(User.organisation_id == organisation_id)

        if client_id:
            if isinstance(client_id, list):
                query = query.filter(User.client_id.in_(client_id))
            else:
                query = query.filter(User.client_id == client_id)

        # Search
        if search:
            query = query.filter(
                or_(
                    User.email.ilike(f"%{search}%"),
                    User.username.ilike(f"%{search}%"),
                    User.first_name.ilike(f"%{search}%"),
                    User.last_name.ilike(f"%{search}%"),
                    func.concat(User.first_name, ' ', User.last_name).ilike(f"%{search}%")
                )
            )

        # Only fetch necessary columns to be "Light"
        # We need ID, Name, Username, Org Name?
        # Org Name might require join.
        query = query.outerjoin(Organisation, User.organisation_id == Organisation.id)
        
        # Select specific fields
        results = query.with_entities(
            User.id, 
            User.first_name, 
            User.last_name, 
            User.username,
            Organisation.name.label("organisation_name")
        ).limit(50).all() # Limit for dropdown performance
        
        return [
            {
                "id": r.id, 
                "first_name": r.first_name, 
                "last_name": r.last_name, 
                "username": r.username,
                "organisation_name": r.organisation_name
            }
            for r in results
        ]

    @staticmethod
    def get_user_by_id(user_id: str, db: Session) -> Optional[Dict]:
        user = db.query(User).filter(
            User.id == user_id,
            ~db.query(UserRole).join(Role).filter(
                UserRole.user_id == User.id,
                Role.name == 'SUPER_ADMIN'
            ).exists()
        ).first()
        if not user:
            return None
        return UserService._format_user_response(user, db)

    @staticmethod
    def get_user_by_email(email: str, db: Session) -> Optional[Dict]:
        user = db.query(User).filter(func.lower(User.email) == email.lower()).first()
        if not user:
            return None
        return UserService._format_user_response(user, db)

    @staticmethod
    def create_user(user_data: Dict, db: Session, current_user: User) -> Dict:
        active_status = db.query(Status).filter(Status.code == 'ACTIVE').first()
        # Fallback if case mismatch or missing
        if not active_status:
             active_status = db.query(Status).filter(Status.code == 'Active').first()
        
        status_id_val = active_status.id if active_status else None

        created_by_val = None
        organisation_id_val = None

        context_org = UserService._ctx_org(current_user)
        context_role = UserService._ctx_role(current_user)
        is_super = UserService._ctx_is_super(current_user)

        created_by_val = None
        organisation_id_val = None
        client_id_val = None

        # SUPERADMIN inside org
        if is_super and context_org:
            created_by_val = str(current_user.id)
            organisation_id_val = str(context_org)

        # GLOBAL SUPERADMIN
        elif is_super and not context_org:
            created_by_val = None
            organisation_id_val = None

        # ROLE-BASED USER
        elif context_role:
            role = db.query(Role).filter(Role.id == context_role).first()

            if role and role.name == "ORGANISATION_ADMIN":
                if not context_org:
                    raise HTTPException(400, "No organisation context")

                created_by_val = str(current_user.id)
                organisation_id_val = str(context_org)

            elif role and role.name == "CLIENT_ADMIN":
                client_id = getattr(current_user, "client_id", None)

                if not client_id:
                    raise HTTPException(400, "Client admin not linked")

                client = db.query(Client).filter(Client.id == client_id).first()

                if not client or not client.organisation_id:
                    raise HTTPException(400, "Client missing org")

                created_by_val = str(current_user.id)
                organisation_id_val = str(client.organisation_id)
                client_id_val = client.id

        else:
            raise HTTPException(403, "User not permitted")


        user = User(
            id=str(uuid.uuid4()),
            email=user_data['email'].lower(),
            username=user_data['username'].lower(),
            hashed_password=get_password_hash(user_data['password']),
            first_name=user_data['first_name'],
            middle_name=user_data.get('middle_name'),
            last_name=user_data['last_name'],
            phone_country_code=user_data.get('phone_country_code'),
            phone_number=user_data.get('phone_number'),
            is_superuser=False,
            status_id=status_id_val,
            organisation_id=organisation_id_val,
            client_id=client_id_val if 'client_id_val' in locals() else user_data.get('client_id'), # Use auto-assigned or provided
            created_by=created_by_val
        )
        
        db.add(user)
        db.commit()
        db.refresh(user)

        # ---- AUTO CLIENT ADMIN ROLE ----
        if user_data.get("client_id"):
            client_admin_role = db.query(Role).filter(Role.name == "CLIENT_ADMIN").first()
            if not client_admin_role:
                raise ValueError("CLIENT_ADMIN role missing in DB")

            UserService._assign_roles(user.id, [client_admin_role.id], db)

        elif user_data.get("role_ids"):
            UserService._assign_roles(user.id, user_data["role_ids"], db)

        # ---- supervisor ----
        if user_data.get("supervisor_id"):
            UserService._assign_supervisor(user.id, user_data["supervisor_id"], db)

        # ---- link client ----
        if user_data.get("client_id"):
            UserService.link_client_owner(db, user.id, user_data["client_id"])

        return user

        # return UserService._format_user_response(user, db)
    @staticmethod
    def link_client_owner(db: Session, user_id: str, client_id: str):
        user = db.query(User).filter(User.id == user_id).first()
        client = db.query(Client).filter(Client.id == client_id).first()

        if not user or not client:
            raise ValueError("User or Client not found")

        # ---- HARD RULES ----
        if user.client_id and user.client_id != client.id:
            raise ValueError("User already linked to another client")

        user.is_client = True

        # db.add(UserClient(
        #     id=str(uuid.uuid4()),
        #     user_id=user.id,
        #     client_id=client.id,
        #     assigned_by=user.id
        # ))

        # ---- OWNERSHIP ONLY ----
        user.client_id = client.id
        user.is_client = True

        client.created_by = user.id
        client.is_user = True

        db.commit()
    # @staticmethod
    # def _link_client(user: User, client_id: str, db: Session):
    #     # Verify client exists
    #     client = db.query(Client).filter(Client.id == client_id).first()
    #     if client:
    #         # Create link
    #         user_client = UserClient(
    #             id=str(uuid.uuid4()),
    #             user_id=user.id,
    #             client_id=client_id,
    #             assigned_by=user.id # Self-assigned via cross-creation
    #         )
    #         db.add(user_client)
            
    #         # Update flags
    #         user.is_client = True
    #         client.is_user = True
            
    #         db.commit()

    @staticmethod
    def get_user_clients(user_id: str, db: Session) -> List[Dict]:
        """Fetch all clients mapped to a specific user"""
        results = db.query(Client).join(UserClient, UserClient.client_id == Client.id).filter(UserClient.user_id == user_id).all()
        
        # We need to format the clients. I'll use a simplified dict for now, 
        # or we could move formatting to ClientService or something similar.
        # But for now, returning simple dicts is fine to match the requirement.
        
        # User defined ClientResponse schema is in clients_router usually or client_service.
        # Since I am in UserService, I will return raw models and let router handle Pydantic conversion 
        # OR return formatted dicts. returning Models is better for Pydantic in Router.
        return results

    @staticmethod
    def map_clients_to_user(user_id: str, client_ids: List[str], assigned_by: Optional[str], db: Session):
        """Map multiple clients to a user"""
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
             raise ValueError("User not found")

        # Get existing mappings to avoid duplicates
        existing_client_ids = {
            str(uc.client_id) for uc in db.query(UserClient.client_id).filter(UserClient.user_id == user_id).all()
        }

        new_mappings = []
        for cid in client_ids:
            if cid not in existing_client_ids:
                 new_mappings.append(UserClient(
                     id=str(uuid.uuid4()),
                     user_id=user_id,
                     client_id=cid,
                     assigned_by=assigned_by
                 ))
        
        if new_mappings:
            db.add_all(new_mappings)
            # Ensure flags are set?
            # If we map a client to a user, does it mean user.is_client = True?
            # Based on _link_client logic:
            # if not user.is_client:
            #     user.is_client = True
            
            # Also update client.is_user?
            # We should probably update the clients too.
            # if new_mappings:
            #      db.query(Client).filter(Client.id.in_(client_ids)).update({Client.is_user: True}, synchronize_session=False)

            db.commit()

    @staticmethod
    def unassign_clients_from_user(user_id: str, client_ids: List[str], db: Session):
        """Unassign multiple clients from a user"""
        if not client_ids:
            return

        # Delete mappings
        db.query(UserClient).filter(
            UserClient.user_id == user_id,
            UserClient.client_id.in_(client_ids)
        ).delete(synchronize_session=False)

        db.commit()

    @staticmethod
    def update_user(user_id: str, user_data: Dict, db: Session, current_user:User) -> Optional[Dict]:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return None
        if not UserService.can_manage_user(current_user, user):
            raise ValueError("Not allowed")

        for key, value in user_data.items():
            if key not in ['role_ids', 'supervisor_id', 'password', 'client_id'] and value is not None:
                if key == 'status_id':
                     # Handle status update safely
                     if isinstance(value, str) and not value.isdigit():
                         status_obj = db.query(Status).filter(Status.code == value).first()
                         if status_obj:
                             user.status_id = status_obj.id
                         # If not found, ignore? or error? ignoring is safer for now.
                     else:
                         user.status_id = value
                elif key == 'email':
                    user.email = value.lower()

                elif key == 'username':
                    user.username = value.lower()
                else:
                    setattr(user, key, value)
        
        if 'role_ids' in user_data and user_data['role_ids'] is not None:
            db.query(UserRole).filter(UserRole.user_id == user_id).delete()
            UserService._assign_roles(user_id, user_data['role_ids'], db)
        
        if 'supervisor_id' in user_data:
            db.query(UserSupervisor).filter(UserSupervisor.user_id == user_id).delete()
            if user_data['supervisor_id']:
                UserService._assign_supervisor(user_id, user_data['supervisor_id'], db)

        # Handle Client Mapping
        # if 'client_id' in user_data:
        #     new_client_id = user_data['client_id']
        #     if new_client_id is None:
        #         db.query(UserClient).filter(UserClient.user_id == user_id).delete()
        #     else:
        #         existing_mapping = db.query(UserClient).filter(UserClient.user_id == user_id).first()
        #         if existing_mapping:
        #             if str(existing_mapping.client_id) != str(new_client_id):
        #                 existing_mapping.client_id = new_client_id
        #                 existing_mapping.assigned_by = current_user.id
        #         else:
        #             new_mapping = UserClient(
        #                 id=str(uuid.uuid4()),
        #                 user_id=user_id,
        #                 client_id=new_client_id,
        #                 assigned_by=current_user.id
        #             )
        #             db.add(new_mapping)
        
        db.commit()
        db.refresh(user)
        return UserService._format_user_response(user, db)
    
    @staticmethod
    def activate_user(user_id: str, db: Session, current_user: User):

        user = db.query(User).filter(User.id == user_id).first()
        if not user or user.is_superuser:
            return None

        if not UserService.can_manage_user(current_user, user):
            raise ValueError("Not allowed")

        active_status = db.query(Status).filter(Status.code == 'ACTIVE').first()

        if active_status:
            user.status_id = active_status.id

            if user.is_client:
                client = db.query(Client).filter(Client.created_by == user.id).first()
                if client:
                    client.status_id = active_status.id

            db.commit()
            db.refresh(user)

        return UserService._format_user_response(user, db)


    @staticmethod
    def can_manage_user(current_user, target_user: User) -> bool:
        context_org = UserService._ctx_org(current_user)
        is_super = UserService._ctx_is_super(current_user)

        # GLOBAL SUPERADMIN
        if is_super and not context_org:
            return True

        # SUPERADMIN inside org
        if is_super and context_org:
            return str(target_user.organisation_id) == str(context_org)

        # USER LOGIN
        if isinstance(current_user, User):
            role_names = [r.name for r in current_user.roles]

            if "ORGANISATION_ADMIN" in role_names:
                if context_org:
                    return str(target_user.organisation_id) == str(context_org)

            if "CLIENT_ADMIN" in role_names:
                return str(target_user.created_by) == str(current_user.id)

        return False


    @staticmethod
    def deactivate_user(user_id: str, db: Session, current_user):
        user = db.query(User).filter(User.id == user_id).first()
        if not user or user.is_superuser:
            return None

        if not UserService.can_manage_user(current_user, user):
            raise ValueError("Not allowed")

        inactive_status = db.query(Status).filter(Status.code == 'INACTIVE').first()

        user.status_id = inactive_status.id

        if user.is_client:
            client = db.query(Client).filter(Client.created_by == user.id).first()
            if client:
                client.status_id = inactive_status.id

        db.commit()
        db.refresh(user)

        return UserService._format_user_response(user, db)


    @staticmethod
    def get_user_stats(db: Session, current_user) -> Dict:

        query = db.query(User).filter(
            ~db.query(UserRole)
            .join(Role)
            .filter(
                UserRole.user_id == User.id,
                Role.name == "SUPER_ADMIN"
            )
            .exists()
        )

        is_super = False
        if isinstance(current_user, User):
            is_super = UserService._ctx_is_super(current_user)

        # Exclude users with ORGANISATION_ADMIN unless the current user is a SUPER_ADMIN
        if not is_super:
            query = query.filter(
                ~db.query(UserRole).join(Role).filter(
                    UserRole.user_id == User.id,
                    Role.name == 'ORGANISATION_ADMIN'
                ).exists()
            )

        # 🔥 SUPERADMIN
        context_org = UserService._ctx_org(current_user)
        is_super = UserService._ctx_is_super(current_user)

        if is_super and not context_org:
            pass

        elif is_super and context_org:
            query = query.filter(User.organisation_id == str(context_org))

        elif isinstance(current_user, User):
            role_names = [r.name for r in current_user.roles]

            if "ORGANISATION_ADMIN" in role_names:
                if context_org:
                    query = query.filter(User.organisation_id == str(context_org))

            elif "CLIENT_ADMIN" in role_names:
                query = query.filter(User.created_by == str(current_user.id))
            
            elif "SUPER_ADMIN" in role_names:
                pass

            else:
                # Standard User -> See NOTHING
                return {
                    "total_users": 0,
                    "active_users": 0,
                    "inactive_users": 0
                }

        total = query.count()

        active_status = db.query(Status).filter(Status.code == "ACTIVE").first()
        inactive_status = db.query(Status).filter(Status.code == "INACTIVE").first()

        active = query.filter(User.status_id == active_status.id).count() if active_status else 0
        inactive = query.filter(User.status_id == inactive_status.id).count() if inactive_status else 0

        return {
            "total_users": total,
            "active_users": active,
            "inactive_users": inactive
        }


    # @staticmethod
    # def get_user_stats(db: Session, current_user: User) -> Dict:
    #     # Exclude SUPER_ADMIN users from all counts
    #     total_users = db.query(func.count(User.id)).filter(
    #         ~db.query(UserRole).join(Role).filter(
    #             UserRole.user_id == User.id,
    #             Role.name == 'SUPER_ADMIN'
    #         ).exists()
    #     ).scalar()
    #     
    #     active_status = db.query(Status).filter(Status.code == 'ACTIVE').first()
    #     active_users = db.query(func.count(User.id)).filter(
    #         User.status_id == active_status.id,
    #         ~db.query(UserRole).join(Role).filter(
    #             UserRole.user_id == User.id,
    #             Role.name == 'SUPER_ADMIN'
    #         ).exists()
    #     ).scalar() if active_status else 0
    #     
    #     admin_users = db.query(func.count(User.id)).filter(
    #         User.is_superuser == True,
    #         ~db.query(UserRole).join(Role).filter(
    #             UserRole.user_id == User.id,
    #             Role.name == 'SUPER_ADMIN'
    #         ).exists()
    #     ).scalar()
    #     
    #     return {
    #         "total_users": total_users,
    #         "active_users": active_users,
    #         "inactive_users": total_users - active_users,
    #         "admin_users": admin_users
    #     }

    @staticmethod
    def check_email_exists(email: str, exclude_id: Optional[str], db: Session) -> bool:
        query = db.query(User).filter(func.lower(User.email) == email.lower())
        if exclude_id:
            query = query.filter(User.id != exclude_id)
        return query.first() is not None

    @staticmethod
    def check_username_exists(username: str, exclude_id: Optional[str], db: Session) -> bool:
        query = db.query(User).filter(func.lower(User.username) == username.lower())
        if exclude_id:
            query = query.filter(User.id != exclude_id)
        return query.first() is not None

    @staticmethod
    def _format_user_response(user: str, db: Session) -> Dict:
        user_roles = db.query(UserRole, Role).join(Role, UserRole.role_id == Role.id).filter(UserRole.user_id == user.id).all()
        roles = [{"id": role.id, "name": role.name} for _, role in user_roles]
        # roles = []
        
        supervisor = db.query(UserSupervisor).filter(UserSupervisor.user_id == user.id).first()
        supervisor_id = supervisor.supervisor_id if supervisor else None
        
        # Load status relationship if not loaded?
        # User model usually doesn't have status relationship defined explicitly in snippet I saw?
        # Let's check User model again if I need to add relationship.
        # Snippet for User model showed `status_id` column but no `status = relationship(...)`?
        # Wait, I checked User model in Step 793, it had:
        # status_id = Column(String, ForeignKey('docucr.status.id'), nullable=True)
        # documents = relationship("Document", back_populates="user")
        # NO `status` relationship!
        # I MUST add status relationship to User model to use `user.status.code`.
        # OR perform a query here.
        
        status_code = None
        if user.status_id:
             status_obj = db.query(Status).filter(Status.id == user.status_id).first()
             if status_obj:
                 status_code = status_obj.code
        client_count = (
            db.query(UserClient).filter(UserClient.user_id == user.id).count()
        )

        # client_count = (
        #     db.query(UserClient).filter(UserClient.user_id == user.id).count()
        #     + db.query(Client).filter(Client.created_by == user.id).count()
        # )


        # Fetch Created By Name
        # created_by_name = None
        # created_by_id = getattr(user, 'created_by', None)
        # if created_by_id:
        #     creator = db.query(User).filter(User.id == created_by_id).first()
        #     if creator:
        #        created_by_name = f"{creator.first_name or ''} {creator.last_name or ''}".strip()
        #        if not created_by_name:
        #            created_by_name = creator.username
        created_by_name = None

        created_by_id = getattr(user, "created_by", None)  # obj = SOP/document/etc

        if created_by_id:
            creator = db.query(User).filter(User.id == created_by_id).first()

            if creator:

                # 🔴 CASE 1: user belongs to organisation → show ORG name
                if creator.organisation_id:
                    org = db.query(Organisation).filter(
                        Organisation.id == creator.organisation_id
                    ).first()

                    if org:
                        created_by_name = org.name
                    else:
                        created_by_name = creator.username

                # 🟢 CASE 2: internal user → show user name
                else:
                    created_by_name = f"{creator.first_name or ''} {creator.last_name or ''}".strip()
                    if not created_by_name:
                        created_by_name = creator.username

        # Fetch Organisation Name
        organisation_name = None
        org_id = user.organisation_id
        if org_id:
             org = db.query(Organisation).filter(Organisation.id == org_id).first()
             if org:
                 # Organisation doesn't have business_name, using first/last or username
                 organisation_name = f"{org.name}".strip()
                 if not organisation_name:
                     organisation_name = org.username

        client_id = None
        client_name = None
        if user.is_client and getattr(user, 'client_id', None):
             client = db.query(Client).filter(Client.id == user.client_id).first()
             if client:
                 client_id = str(client.id)

        return {
            "id": user.id,
            "email": user.email,
            "username": user.username,
            "first_name": user.first_name,
            "middle_name": user.middle_name,
            "last_name": user.last_name,
            "phone_country_code": user.phone_country_code,
            "phone_number": user.phone_number,
            "status_id": user.status_id, # Integer
            "statusCode": status_code,   # String
            "is_superuser": user.is_superuser or False,
            "roles": roles,
            "supervisor_id": supervisor_id,
            "assigned_client_count": client_count,
            "client_count": client_count,
            "created_by_name": created_by_name,
            "organisation_name": organisation_name,
            "client_id": client_id,
            "profile_image_url": user.profile_image_url
        }

    @staticmethod
    def _format_user_response_for_me(current_user: User, db: Session) -> Dict:
        context_role_id = getattr(current_user, "context_role_id", None)

        roles = []
        if context_role_id:
            role = db.query(Role).filter(Role.id == context_role_id).first()
            if role:
                roles = [{"id": role.id, "name": role.name}]
                # roles = []
        
        supervisor = db.query(UserSupervisor).filter(UserSupervisor.user_id == current_user.id).first()
        supervisor_id = supervisor.supervisor_id if supervisor else None
        
        status_code = None
        if current_user.status_id:
             status_obj = db.query(Status).filter(Status.id == current_user.status_id).first()
             if status_obj:
                 status_code = status_obj.code
        client_count = (
            db.query(UserClient).filter(UserClient.user_id == current_user.id).count()
        )

        # Fetch Created By Name
        created_by_name = None
        created_by_id = getattr(current_user, 'created_by', None)
        if created_by_id:
            creator = db.query(User).filter(User.id == created_by_id).first()
            if creator:
               created_by_name = f"{creator.first_name or ''} {creator.last_name or ''}".strip()
               if not created_by_name:
                   created_by_name = creator.username

        # Fetch Organisation Name
        organisation_name = None
        org_id = getattr(current_user, 'context_organisation_id', None)
        if org_id:
             org = db.query(Organisation).filter(Organisation.id == org_id).first()
             if org:
                 # Organisation doesn't have business_name, using first/last or username
                 organisation_name = f"{org.name}".strip()
                 if not organisation_name:
                     organisation_name = org.name

        role_id = getattr(current_user, "context_role_id", None)
        role = db.query(Role).filter(Role.id == role_id).first()
        role_name = role.name if role else ""

        client_id = None
        client_name = None

        if role_name == "CLIENT_ADMIN":
            if current_user.client_id:
                client = db.query(Client).filter(Client.id == current_user.client_id).first()
                if client:
                    client_id = str(client.id)
        else:
            if current_user.created_by:
                client_id = str(current_user.created_by)

        return {
            "id": current_user.id,
            "email": current_user.email,
            "username": current_user.username,
            "first_name": current_user.first_name,
            "middle_name": current_user.middle_name,
            "last_name": current_user.last_name,
            "phone_country_code": current_user.phone_country_code,
            "phone_number": current_user.phone_number,
            "status_id": current_user.status_id, # Integer
            "statusCode": status_code,   # String
            "is_superuser": getattr(current_user, "context_is_superadmin", current_user.is_superuser),
            "roles": roles,
            "supervisor_id": supervisor_id,
            "assigned_client_count": client_count,
            "client_count": client_count,
            "created_by_name": created_by_name,
            "organisation_name": organisation_name,
            "client_id": client_id,
            "profile_image_url": current_user.profile_image_url
        }

    @staticmethod
    def _assign_roles(user_id: str, role_ids: List[str], db: Session):
        for role_id in role_ids:
            user_role = UserRole(
                id=str(uuid.uuid4()),
                user_id=user_id,
                role_id=role_id
            )
            db.add(user_role)
        db.commit()

    # @staticmethod
    # def _assign_supervisor(user_id: str, supervisor_id: str, db: Session):
    #     supervisor = UserSupervisor(
    #         id=str(uuid.uuid4()),
    #         user_id=user_id,
    #         supervisor_id=supervisor_id
    #     )
    #     db.add(supervisor)
    #     db.commit()
    @staticmethod
    def _assign_supervisor(user_id: str, supervisor_id: str, db: Session):
        if user_id == supervisor_id:
            raise ValueError("User cannot be their own supervisor")

        supervisor = db.query(User).filter(User.id == supervisor_id).first()
        if not supervisor:
            raise ValueError("Supervisor not found")

        # Validate shared role - REMOVED as it prevents valid cross-role supervision
        # user_roles = {
        #     r.role_id for r in db.query(UserRole).filter(UserRole.user_id == user_id)
        # }
        # supervisor_roles = {
        #     r.role_id for r in db.query(UserRole).filter(UserRole.user_id == supervisor_id)
        # }

        # if not user_roles.intersection(supervisor_roles):
        #     raise ValueError("Supervisor must share at least one role with user")

        db.add(UserSupervisor(
            id=str(uuid.uuid4()),
            user_id=user_id,
            supervisor_id=supervisor_id
        ))

        db.commit()
    @staticmethod
    def resolve_org_id(current_user):
        if isinstance(current_user, User):
            return str(current_user.id) if current_user.id else None
        return None


    @staticmethod
    def change_password(user_id: str, new_password: str, db: Session) -> bool:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return False
        
        user.hashed_password = get_password_hash(new_password)
        db.commit()
        return True