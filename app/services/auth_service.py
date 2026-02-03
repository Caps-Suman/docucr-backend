from collections import defaultdict
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from typing import Optional, Dict, List
import random
import string
import uuid

from app.models.client import Client
from app.models.module import Module
from app.models.privilege import Privilege
from app.models.role_module import RoleModule
from app.models.role_submodule import RoleSubmodule
from app.models.submodule import Submodule
from app.models.user import User
from app.models.otp import OTP
from app.models.user_client import UserClient
from app.models.user_role import UserRole
from app.models.role import Role
from app.models.status import Status
from app.core.security import verify_password, create_access_token, create_refresh_token, get_password_hash
from app.utils.email import send_otp_email
from datetime import timezone

class AuthService:
    @staticmethod
    def authenticate_user(email: str, password: str, db: Session) -> Optional[User]:
        user = db.query(User).filter(User.email == email).first()
        if not user or not verify_password(password, user.hashed_password):
            return None
        return user

    @staticmethod
    def check_user_active(user: User, db: Session) -> bool:
        active_status = db.query(Status).filter(Status.code == 'ACTIVE').first()
        return active_status and user.status_id == active_status.id
    
    @staticmethod
    def get_role_permissions(role_id: str, db: Session) -> dict:
        permissions = defaultdict(set)

        # Module-level permissions
        module_perms = (
            db.query(Module.name, Privilege.name)
            .join(RoleModule, RoleModule.module_id == Module.id)
            .join(Privilege, RoleModule.privilege_id == Privilege.id)
            .filter(RoleModule.role_id == role_id)
            .all()
        )

        for module_name, privilege_name in module_perms:
            permissions[module_name.upper()].add(privilege_name.upper())

        # Submodule-level permissions
        submodule_perms = (
            db.query(Submodule.route_key, Privilege.name)
            .join(RoleSubmodule, RoleSubmodule.submodule_id == Submodule.id)
            .join(Privilege, RoleSubmodule.privilege_id == Privilege.id)
            .filter(RoleSubmodule.role_id == role_id)
            .all()
        )

        for route_key, privilege_name in submodule_perms:
            permissions[route_key.upper()].add(privilege_name.upper())

        # convert sets → sorted lists
        return {k: sorted(v) for k, v in permissions.items()}

    @staticmethod
    def get_user_client(user_id: str, db: Session) -> Optional[Client]:
        return (
            db.query(Client)
            .join(UserClient, UserClient.client_id == Client.id)
            .filter(UserClient.user_id == user_id)
            .one_or_none()
        )
    @staticmethod
    def get_client_by_id(client_id: str, db: Session):
        return db.query(Client).filter(Client.id == client_id).one_or_none()

    @staticmethod
    def get_user_roles(user_id: str, db: Session) -> List[Dict]:
        active_status = db.query(Status).filter(Status.code == 'ACTIVE').first()
        user_roles = db.query(UserRole, Role).join(Role, UserRole.role_id == Role.id).filter(
            UserRole.user_id == user_id,
            Role.status_id == active_status.id
        ).all()
        return [{"id": role.id, "name": role.name} for _, role in user_roles]

    @staticmethod
    def generate_tokens(email: str, role_id: str) -> Dict:
        access_token = create_access_token(data={"sub": email, "role_id": role_id})
        refresh_token = create_refresh_token(data={"sub": email, "role_id": role_id})
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "expires_in": 3600
        }

    @staticmethod
    def verify_user_role(user_id: str, role_id: str, db: Session) -> Optional[Role]:
        active_status = db.query(Status).filter(Status.code == 'ACTIVE').first()
        user_role = db.query(UserRole, Role).join(Role, UserRole.role_id == Role.id).filter(
            UserRole.user_id == user_id,
            UserRole.role_id == role_id,
            Role.status_id == active_status.id
        ).first()
        return user_role[1] if user_role else None

    @staticmethod
    def generate_otp(email: str, db: Session) -> str:
        otp_code = ''.join(random.choices(string.digits, k=6))
        # Use timezone-aware UTC
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)

        otp_record = db.query(OTP).filter(OTP.email == email).first()
        if otp_record:
            otp_record.otp_code = otp_code
            otp_record.expires_at = expires_at
            otp_record.is_used = False
        else:
            new_otp = OTP(
                id=str(uuid.uuid4()),
                email=email,
                otp_code=otp_code,
                expires_at=expires_at,
                is_used=False
            )
            db.add(new_otp)
        db.commit()
        return otp_code

    @staticmethod
    def verify_otp(email: str, otp: str, db: Session) -> bool:
        otp_record = db.query(OTP).filter(OTP.email == email, OTP.otp_code == otp).first()
        if not otp_record or otp_record.is_used or otp_record.expires_at < datetime.now(timezone.utc):
            return False
        return True

    @staticmethod
    def reset_user_password(email: str, otp: str, new_password: str, db: Session) -> bool:
        otp_record = db.query(OTP).filter(OTP.email == email, OTP.otp_code == otp).first()
        if not otp_record:
            return False

        user = db.query(User).filter(User.email == email).first()
        if not user:
            return False

        user.hashed_password = get_password_hash(new_password)
        otp_record.is_used = True
        db.commit()
        return True
