from fastapi import Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from jose import jwt
from app.core.database import get_db
from app.core.security import get_current_user, SECRET_KEY, ALGORITHM
from app.models.user import User
from app.models.role_module import RoleModule
from app.models.role_submodule import RoleSubmodule
from app.models.module import Module
from app.models.submodule import Submodule
from app.models.privilege import Privilege

class Permission:
    def __init__(self, module: str, privilege: str):
        self.module_name = module
        self.privilege_name = privilege

    async def __call__(
        self,
        user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
    ):
        if user.is_superuser:
            return user

        if not user.role_id:
            raise HTTPException(403, "No active role selected")

        # module-level
        module_perm = (
            db.query(RoleModule)
            .join(Module)
            .join(Privilege)
            .filter(
                RoleModule.role_id == user.role_id,
                Module.name == self.module_name,
                Privilege.name.in_([self.privilege_name, "MANAGE", "ADMIN"])
            )
            .first()
        )

        if module_perm:
            return user

        # submodule-level
        submodule_perm = (
            db.query(RoleSubmodule)
            .join(Submodule)
            .join(Privilege)
            .filter(
                RoleSubmodule.role_id == user.role_id,
                Submodule.route_key == self.module_name,
                Privilege.name.in_([self.privilege_name, "MANAGE", "ADMIN"])
            )
            .first()
        )

        if not submodule_perm:
            raise HTTPException(403, "You do not have enough access permission")

        return user
