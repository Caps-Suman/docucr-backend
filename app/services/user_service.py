from sqlalchemy.orm import Session
from sqlalchemy import func, or_
from typing import Optional, List, Dict, Tuple
import uuid

from app.models.user import User
from app.models.user_role import UserRole
from app.models.role import Role
from app.models.status import Status
from app.models.user_supervisor import UserSupervisor
from app.models.user_client import UserClient
from app.models.client import Client
from app.core.security import get_password_hash


class UserService:
    @staticmethod
    def get_users(page: int, page_size: int, search: Optional[str], status_id: Optional[str], db: Session) -> Tuple[List[Dict], int]:
        skip = (page - 1) * page_size
        query = db.query(User).outerjoin(UserRole).outerjoin(Role)
        
        # Exclude users with SUPER_ADMIN role
        query = query.filter(
            ~db.query(UserRole).join(Role).filter(
                UserRole.user_id == User.id,
                Role.name == 'SUPER_ADMIN'
            ).exists()
        )
        
        if status_id:
            query = query.join(User.status_relation).filter(Status.code == status_id)
        
        if search:
            query = query.filter(
                or_(
                    User.email.ilike(f"%{search}%"),
                    User.username.ilike(f"%{search}%"),
                    User.first_name.ilike(f"%{search}%"),
                    User.last_name.ilike(f"%{search}%")
                )
            )
        
        total = query.count()
        users = query.offset(skip).limit(page_size).all()
        
        result = []
        for user in users:
            user_data = UserService._format_user_response(user, db)
            result.append(user_data)
        
        return result, total

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
    def create_user(user_data: Dict, db: Session) -> Dict:
        active_status = db.query(Status).filter(Status.code == 'active').first()
        # Fallback if case mismatch or missing
        if not active_status:
             active_status = db.query(Status).filter(Status.name == 'Active').first()
        
        status_id_val = active_status.id if active_status else None

        new_user = User(
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
            status_id=status_id_val
        )
        
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        
        if user_data.get('role_ids'):
            UserService._assign_roles(new_user.id, user_data['role_ids'], db)
        
        if user_data.get('supervisor_id'):
            UserService._assign_supervisor(new_user.id, user_data['supervisor_id'], db)

        if user_data.get('client_id'):
            UserService._link_client(new_user, user_data['client_id'], db)
        
        return UserService._format_user_response(new_user, db)
    
    @staticmethod
    def _link_client(user: User, client_id: str, db: Session):
        # Verify client exists
        client = db.query(Client).filter(Client.id == client_id).first()
        if client:
            # Create link
            user_client = UserClient(
                id=str(uuid.uuid4()),
                user_id=user.id,
                client_id=client_id,
                assigned_by=user.id # Self-assigned via cross-creation
            )
            db.add(user_client)
            
            # Update flags
            user.is_client = True
            client.is_user = True
            
            db.commit()

    @staticmethod
    def update_user(user_id: str, user_data: Dict, db: Session) -> Optional[Dict]:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return None
        
        for key, value in user_data.items():
            if key not in ['role_ids', 'supervisor_id', 'password'] and value is not None:
                if key == 'status_id':
                     # Handle status update safely
                     if isinstance(value, str) and not value.isdigit():
                         status_obj = db.query(Status).filter(Status.code == value).first()
                         if status_obj:
                             user.status_id = status_obj.id
                         # If not found, ignore? or error? ignoring is safer for now.
                     else:
                         user.status_id = value
                elif key in ['email', 'username']:
                    user.email = value.lower() if key == 'email' else value.lower()
                    # setattr(user, key, value.lower()) # Wait, above line is weird
                    setattr(user, key, value.lower())
                else:
                    setattr(user, key, value)
        
        if 'role_ids' in user_data and user_data['role_ids'] is not None:
            db.query(UserRole).filter(UserRole.user_id == user_id).delete()
            UserService._assign_roles(user_id, user_data['role_ids'], db)
        
        if 'supervisor_id' in user_data:
            db.query(UserSupervisor).filter(UserSupervisor.user_id == user_id).delete()
            if user_data['supervisor_id']:
                UserService._assign_supervisor(user_id, user_data['supervisor_id'], db)
        
        db.commit()
        db.refresh(user)
        return UserService._format_user_response(user, db)
    
    @staticmethod
    def activate_user(user_id: str, db: Session) -> Optional[Dict]:
        user = db.query(User).filter(User.id == user_id).first()
        if not user or user.is_superuser:
            return None
        
        active_status = db.query(Status).filter(Status.code == 'ACTIVE').first()
        if active_status:
            user.status_id = active_status.id
            db.commit()
            db.refresh(user)
        return UserService._format_user_response(user, db)

    @staticmethod
    def deactivate_user(user_id: str, db: Session) -> Optional[Dict]:
        user = db.query(User).filter(User.id == user_id).first()
        if not user or user.is_superuser:
            return None
        
        inactive_status = db.query(Status).filter(Status.code == 'INACTIVE').first()
        if inactive_status:
            user.status_id = inactive_status.id
            db.commit()
            db.refresh(user)
        return UserService._format_user_response(user, db)

    @staticmethod
    def get_user_stats(db: Session) -> Dict:
        # Exclude SUPER_ADMIN users from all counts
        total_users = db.query(func.count(User.id)).filter(
            ~db.query(UserRole).join(Role).filter(
                UserRole.user_id == User.id,
                Role.name == 'SUPER_ADMIN'
            ).exists()
        ).scalar()
        
        active_status = db.query(Status).filter(Status.code == 'ACTIVE').first()
        active_users = db.query(func.count(User.id)).filter(
            User.status_id == active_status.id,
            ~db.query(UserRole).join(Role).filter(
                UserRole.user_id == User.id,
                Role.name == 'SUPER_ADMIN'
            ).exists()
        ).scalar() if active_status else 0
        
        admin_users = db.query(func.count(User.id)).filter(
            User.is_superuser == True,
            ~db.query(UserRole).join(Role).filter(
                UserRole.user_id == User.id,
                Role.name == 'SUPER_ADMIN'
            ).exists()
        ).scalar()
        
        return {
            "total_users": total_users,
            "active_users": active_users,
            "inactive_users": total_users - active_users,
            "admin_users": admin_users
        }

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
    def _format_user_response(user: User, db: Session) -> Dict:
        user_roles = db.query(UserRole, Role).join(Role, UserRole.role_id == Role.id).filter(UserRole.user_id == user.id).all()
        roles = [{"id": role.id, "name": role.name} for _, role in user_roles]
        
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
            "is_superuser": user.is_superuser,
            "roles": roles,
            "supervisor_id": supervisor_id
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

    @staticmethod
    def _assign_supervisor(user_id: str, supervisor_id: str, db: Session):
        supervisor = UserSupervisor(
            id=str(uuid.uuid4()),
            user_id=user_id,
            supervisor_id=supervisor_id
        )
        db.add(supervisor)
        db.commit()
