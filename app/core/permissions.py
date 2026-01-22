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

    async def __call__(self, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
        if user.is_superuser:
            return True

        auth_header = request.headers.get("Authorization")
        if not auth_header:
            raise HTTPException(status_code=401, detail="Missing authorization header")
            
        try:
            token = auth_header.split(" ")[1]
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            role_id = payload.get("role_id")
        except Exception:
            raise HTTPException(status_code=401, detail="Invalid token")

        if not role_id:
            raise HTTPException(status_code=403, detail="No active role selected")

        # Check if user has specific privilege OR 'ADMIN' OR 'MANAGE' privilege
        # Check Module Level Permission
        module_perm = (
            db.query(RoleModule)
            .join(Module, RoleModule.module_id == Module.id)
            .join(Privilege, RoleModule.privilege_id == Privilege.id)
            .filter(
                RoleModule.role_id == role_id,
                Module.name == self.module_name,
                Privilege.name.in_([self.privilege_name, "MANAGE", "ADMIN"])
            )
            .first()
        )

        if module_perm:
            return True

        # Check Submodule Level Permission (checking against route_key or name)
        submodule_perm = (
            db.query(RoleSubmodule)
            .join(Submodule, RoleSubmodule.submodule_id == Submodule.id)
            .join(Privilege, RoleSubmodule.privilege_id == Privilege.id)
            .filter(
                RoleSubmodule.role_id == role_id,
                (Submodule.name == self.module_name) | (Submodule.route_key == self.module_name),
                Privilege.name.in_([self.privilege_name, "MANAGE", "ADMIN"])
            )
            .first()
        )
        
        permission = module_perm or submodule_perm

        if not permission:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"You do not have permission to {self.privilege_name.lower()} {self.module_name}."
            )

        return True
