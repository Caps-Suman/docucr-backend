from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session
from jose import jwt
from sqlalchemy import func
from app.core.database import get_db
from app.core.security import get_current_user, SECRET_KEY, ALGORITHM
from app.models.user import User
from app.models.role_module import RoleModule
from app.models.role_submodule import RoleSubmodule
from app.models.module import Module
from app.models.submodule import Submodule
from app.models.privilege import Privilege

security = HTTPBearer()

def get_current_role_id(
        credentials: HTTPAuthorizationCredentials = Depends(security),
    ) -> str:
        try:
            payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
            role_id = payload.get("role_id")
            if not role_id:
                raise HTTPException(403, "No active role selected")
            return role_id
        except Exception:
            raise HTTPException(401, "Invalid token")
class Permission:
    def __init__(self, module: str, privilege: str):
        self.module_name = module.lower().strip()
        self.privilege_name = privilege.upper().strip()

    async def __call__(
        self,
        user: User = Depends(get_current_user),
        role_id: str = Depends(get_current_role_id),
        db: Session = Depends(get_db),
    ):

        if user.is_superuser:
            return user

        # MODULE level
        module_perm = (
            db.query(RoleModule)
            .join(Module)
            .join(Privilege)
            .filter(
                RoleModule.role_id == role_id,
                func.lower(Module.name) == self.module_name,
                func.upper(Privilege.name).in_([
                    self.privilege_name,
                    "MANAGE",
                    "ADMIN"
                ]),
            )
            .first()
        )

        if module_perm:
            return user

        # SUBMODULE level
        submodule_perm = (
            db.query(RoleSubmodule)
            .join(Submodule)
            .join(Privilege)
            .filter(
                RoleSubmodule.role_id == role_id,
                func.lower(Submodule.name) == self.module_name,
                func.upper(Privilege.name).in_([
                    self.privilege_name,
                    "MANAGE",
                    "ADMIN"
                ]),
            )
            .first()
        )

        if not submodule_perm:
            raise HTTPException(403, "You do not have enough access permission")

        return user