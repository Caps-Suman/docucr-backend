<<<<<<< HEAD
from fastapi import APIRouter, HTTPException, Depends, Request, BackgroundTasks
from sqlalchemy.orm import Session
from datetime import timedelta
from pydantic import BaseModel
from typing import Optional

from app.core.database import get_db
from app.core.security import get_current_user
from app.models import user
from app.models import user
from app.services.auth_service import AuthService
from app.services.activity_service import ActivityService
from app.models.user import User

router = APIRouter()

class LoginRequest(BaseModel):
    email: str
    password: str
    remember_me: bool = False

class RoleSelectionRequest(BaseModel):
    email: str
    role_id: str
    remember_me: bool = False

class ForgotPasswordRequest(BaseModel):
    email: str

class TwoFactorRequest(BaseModel):
    email: str
    otp: str

class ResetPasswordRequest(BaseModel):
    email: str
    otp: str
    new_password: str

@router.post("/login")
async def login(request: LoginRequest, req: Request, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    user = AuthService.authenticate_user(request.email, request.password, db)
    if not user:
        ActivityService.log(
            db, 
            action="LOGIN_FAILED", 
            entity_type="user", 
            details={"email": request.email}, 
            request=req,
            background_tasks=background_tasks
        )
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    if not AuthService.check_user_active(user, db):
        raise HTTPException(status_code=403, detail="Account is inactive")

    # Check for SUPER_ADMIN role to bypass 2FA
    roles = AuthService.get_user_roles(user.id, db)
    is_super_admin = any(role["name"] == "SUPER_ADMIN" for role in roles)

    if is_super_admin:
        ActivityService.log(
            db,
            action="LOGIN",
            entity_type="user",
            entity_id=user.id,
            user_id=user.id,
            request=req,
            background_tasks=background_tasks
        )

        if len(roles) == 1:
            tokens = AuthService.generate_tokens(user.email, roles[0]["id"])
            client_name = None
            if user.is_client and user.client_id:
                client = AuthService.get_client_by_id(user.client_id, db)
                if client:
                    client_name = client.business_name or f"{client.first_name} {client.last_name}".strip()

            return {
                **tokens,
                "user": {
                    "id": user.id,
                    "email": user.email,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                    "role": roles[0],
                    "is_client": user.is_client,
                    "client_id": user.client_id,
                    "client_name": client_name
                }
            }
        
        from app.core.security import create_access_token
        temp_token = create_access_token(data={"sub": user.email, "temp": True}, expires_delta=timedelta(minutes=5))
        
        return {
            "requires_role_selection": True,
            "temp_token": temp_token,
            "roles": roles,
            "user": {
                "id": user.id,
                "email": user.email,
                "first_name": user.first_name,
                "last_name": user.last_name
            }
        }

    # Regular 2FA flow for non-super admins
    try:
        AuthService.generate_2fa_otp(request.email, db)
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to send 2FA code")
        
    ActivityService.log(
        db,
        action="2FA_SENT",
        entity_type="user",
        entity_id=user.id,
        user_id=user.id,
        request=req,
        background_tasks=background_tasks
    )

    from app.core.security import create_access_token
    temp_token = create_access_token(data={"sub": user.email, "temp": True, "2fa": True}, expires_delta=timedelta(minutes=10))
    
    return {
        "requires_2fa": True,
        "temp_token": temp_token,
        "message": "2FA code sent to your email"
    }

@router.post("/verify-2fa")
async def verify_2fa(request: TwoFactorRequest, req: Request, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    if not AuthService.verify_2fa_otp(request.email, request.otp, db):
        ActivityService.log(
            db,
            action="2FA_FAILED",
            entity_type="user",
            details={"email": request.email},
            request=req,
            background_tasks=background_tasks
        )
        raise HTTPException(status_code=400, detail="Invalid or expired 2FA code")
    
    user = db.query(User).filter(User.email == request.email).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    if not AuthService.check_user_active(user, db):
        raise HTTPException(status_code=403, detail="Account is inactive")
        
    ActivityService.log(
        db,
        action="LOGIN",
        entity_type="user",
        entity_id=user.id,
        user_id=user.id,
        request=req,
        background_tasks=background_tasks
    )

    roles = AuthService.get_user_roles(user.id, db)
    
    if not roles:
        raise HTTPException(status_code=403, detail="No active roles assigned")
    
    if len(roles) == 1:
        tokens = AuthService.generate_tokens(user.email, roles[0]["id"])
        client = None
        client_name = None

        if user.is_client and user.client_id:
            client = AuthService.get_client_by_id(user.client_id, db)
            if client:
                client_name = (
                    client.business_name
                    or f"{client.first_name} {client.last_name}".strip()
                )

        return {
            **tokens,
            "user": {
                "id": user.id,
                "email": user.email,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "role": roles[0],
                "is_client": user.is_client,
                "client_id": user.client_id,
                "client_name": client_name
            }
        }
    
    from app.core.security import create_access_token
    temp_token = create_access_token(data={"sub": user.email, "temp": True}, expires_delta=timedelta(minutes=5))
    
    return {
        "requires_role_selection": True,
        "temp_token": temp_token,
        "roles": roles,
        "user": {
            "id": user.id,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name
        }
    }

@router.post("/resend-2fa")
async def resend_2fa(request: LoginRequest, req: Request, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    user = AuthService.authenticate_user(request.email, request.password, db)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    if not AuthService.check_user_active(user, db):
        raise HTTPException(status_code=403, detail="Account is inactive")

    try:
        AuthService.generate_2fa_otp(request.email, db)
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to resend 2FA code")
        
    ActivityService.log(
        db,
        action="2FA_RESENT",
        entity_type="user",
        entity_id=user.id,
        user_id=user.id,
        request=req,
        background_tasks=background_tasks
    )
    
    return {"message": "2FA code resent to your email"}

@router.post("/select-role")
async def select_role(request: RoleSelectionRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if current_user.email != request.email:
        raise HTTPException(status_code=403, detail="Unauthorized to select role for this user")
    
    if not AuthService.check_user_active(current_user, db):
        raise HTTPException(status_code=403, detail="Account is inactive")
    
    role = AuthService.verify_user_role(current_user.id, request.role_id, db)
    if not role:
        raise HTTPException(status_code=403, detail="User does not have this role")
    
    tokens = AuthService.generate_tokens(current_user.email, request.role_id)
    
    client_id = None
    client_name = None

    if current_user.is_client:
        client = AuthService.get_client_by_id(current_user.client_id, db)
        if client:
            client_id = str(client.id)
            client_name = (
                client.business_name
                or f"{client.first_name} {client.last_name}".strip()
            )

    return {
        **tokens,
        "user": {
            "id": current_user.id,
            "email": current_user.email,
            "first_name": current_user.first_name,
            "last_name": current_user.last_name,
            "role": {"id": role.id, "name": role.name},
            "is_client": current_user.is_client,
            "client_id": current_user.client_id,
            "client_name": client_name
        }
    }


@router.post("/forgot-password")
async def forgot_password(request: ForgotPasswordRequest, req: Request, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    from app.services.user_service import UserService
    from app.utils.email import send_otp_email
    
    user = UserService.get_user_by_email(request.email, db)
    if not user:
        # Log attempt for non-existent user? Maybe strictly for security auditing but optional here.
        raise HTTPException(status_code=404, detail="User not found")

    otp_code = AuthService.generate_otp(request.email, db)
    sent = send_otp_email(request.email, otp_code)
    
    if sent:
        ActivityService.log(
            db,
            action="FORGOT_PASSWORD_REQUEST",
            entity_type="user",
            entity_id=user["id"], # UserService returns dict
            user_id=user["id"],
            details={"email": request.email},
            request=req,
            background_tasks=background_tasks
        )
        return {"message": "OTP sent to your email"}
    else:
        raise HTTPException(status_code=500, detail="Failed to send email")

@router.post("/reset-password")
async def reset_password(request: ResetPasswordRequest, req: Request, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    if not AuthService.verify_otp(request.email, request.otp, db):
        raise HTTPException(status_code=400, detail="Invalid or expired OTP")
    
    if not AuthService.reset_user_password(request.email, request.otp, request.new_password, db):
        raise HTTPException(status_code=404, detail="User not found")
        
    ActivityService.log(
        db,
        action="RESET_PASSWORD",
        entity_type="user",
        details={"email": request.email},
        request=req,
        background_tasks=background_tasks
    )
    
    return {"message": "Password reset successfully"}

@router.post("/refresh")
async def refresh_token(request: Request, db: Session = Depends(get_db)):
    from jose import jwt, JWTError
    from app.core.security import SECRET_KEY, ALGORITHM, create_access_token, create_refresh_token
    
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing refresh token")
    token = auth_header.split(" ")[1]
    
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid token type")
        email = payload.get("sub")
        role_id = payload.get("role_id")
        if not email:
            raise HTTPException(status_code=401, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")
    
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    
    if not AuthService.check_user_active(user, db):
        raise HTTPException(status_code=403, detail="Account is inactive")
    
    new_access_token = create_access_token(data={"sub": email, "role_id": role_id})
    new_refresh_token = create_refresh_token(data={"sub": email, "role_id": role_id})
    
    return {
        "access_token": new_access_token,
        "refresh_token": new_refresh_token,
        "token_type": "bearer",
        "expires_in": 3600
=======
from fastapi import APIRouter, HTTPException, Depends, Request, BackgroundTasks
from sqlalchemy.orm import Session
from datetime import timedelta
from pydantic import BaseModel
from typing import Optional

from app.core.database import get_db
from app.core.security import get_current_user
from app.models import user
from app.models import user
from app.services.auth_service import AuthService
from app.services.activity_service import ActivityService
from app.models.user import User

router = APIRouter()

class LoginRequest(BaseModel):
    email: str
    password: str
    remember_me: bool = False

class RoleSelectionRequest(BaseModel):
    email: str
    role_id: str
    remember_me: bool = False

class ForgotPasswordRequest(BaseModel):
    email: str

class ResetPasswordRequest(BaseModel):
    email: str
    otp: str
    new_password: str

@router.post("/login")
async def login(request: LoginRequest, req: Request, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    user = AuthService.authenticate_user(request.email, request.password, db)
    if not user:
        # Optional: Log failed login attempt
        ActivityService.log(
            db, 
            action="LOGIN_FAILED", 
            entity_type="user", 
            details={"email": request.email}, 
            request=req,
            background_tasks=background_tasks
        )
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    if not AuthService.check_user_active(user, db):
        raise HTTPException(status_code=403, detail="Account is inactive")
        
    ActivityService.log(
        db,
        action="LOGIN",
        entity_type="user",
        entity_id=user.id,
        user_id=user.id,
        request=req,
        background_tasks=background_tasks
    )

    roles = AuthService.get_user_roles(user.id, db)
    
    if not roles:
        raise HTTPException(status_code=403, detail="No active roles assigned")
    
    if len(roles) == 1:
        tokens = AuthService.generate_tokens(user.email, roles[0]["id"])
        permissions = AuthService.get_role_permissions(roles[0]["id"], db)
        client = None
        client_name = None

        if user.is_client and user.client_id:
            client = AuthService.get_client_by_id(user.client_id, db)
            if client:
                client_name = (
                    client.business_name
                    or f"{client.first_name} {client.last_name}".strip()
                )

        return {
            **tokens,
            "user": {
                "id": user.id,
                "email": user.email,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "role": roles[0],
                "is_client": user.is_client,
                "client_id": user.client_id,
                "client_name": client_name,
                "permissions": permissions 
            }
        }
    
    from app.core.security import create_access_token
    temp_token = create_access_token(data={"sub": user.email, "temp": True}, expires_delta=timedelta(minutes=5))
    
    return {
        "requires_role_selection": True,
        "temp_token": temp_token,
        "roles": roles,
        "user": {
            "id": user.id,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name
        }
    }

@router.post("/select-role")
async def select_role(request: RoleSelectionRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if current_user.email != request.email:
        raise HTTPException(status_code=403, detail="Unauthorized to select role for this user")
    
    if not AuthService.check_user_active(current_user, db):
        raise HTTPException(status_code=403, detail="Account is inactive")
    
    role = AuthService.verify_user_role(current_user.id, request.role_id, db)
    if not role:
        raise HTTPException(status_code=403, detail="User does not have this role")
    
    tokens = AuthService.generate_tokens(current_user.email, request.role_id)
    permissions = AuthService.get_role_permissions(role.id, db)

    client_id = None
    client_name = None

    if current_user.is_client:
        client = AuthService.get_client_by_id(current_user.client_id, db)
        if client:
            client_id = str(client.id)
            client_name = (
                client.business_name
                or f"{client.first_name} {client.last_name}".strip()
            )

    return {
        **tokens,
        "user": {
            "id": current_user.id,
            "email": current_user.email,
            "first_name": current_user.first_name,
            "last_name": current_user.last_name,
            "role": {"id": role.id, "name": role.name},
            "is_client": current_user.is_client,
            "client_id": current_user.client_id,
            "client_name": client_name,
            "permissions": permissions
        }
    }


@router.post("/forgot-password")
async def forgot_password(request: ForgotPasswordRequest, req: Request, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    from app.services.user_service import UserService
    from app.utils.email import send_otp_email
    
    user = UserService.get_user_by_email(request.email, db)
    if not user:
        # Log attempt for non-existent user? Maybe strictly for security auditing but optional here.
        raise HTTPException(status_code=404, detail="User not found")

    otp_code = AuthService.generate_otp(request.email, db)
    sent = send_otp_email(request.email, otp_code)
    
    if sent:
        ActivityService.log(
            db,
            action="FORGOT_PASSWORD_REQUEST",
            entity_type="user",
            entity_id=user["id"], # UserService returns dict
            user_id=user["id"],
            details={"email": request.email},
            request=req,
            background_tasks=background_tasks
        )
        return {"message": "OTP sent to your email"}
    else:
        raise HTTPException(status_code=500, detail="Failed to send email")

@router.post("/reset-password")
async def reset_password(request: ResetPasswordRequest, req: Request, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    if not AuthService.verify_otp(request.email, request.otp, db):
        raise HTTPException(status_code=400, detail="Invalid or expired OTP")
    
    if not AuthService.reset_user_password(request.email, request.otp, request.new_password, db):
        raise HTTPException(status_code=404, detail="User not found")
        
    ActivityService.log(
        db,
        action="RESET_PASSWORD",
        entity_type="user",
        details={"email": request.email},
        request=req,
        background_tasks=background_tasks
    )
    
    return {"message": "Password reset successfully"}

@router.post("/refresh")
async def refresh_token(request: Request, db: Session = Depends(get_db)):
    from jose import jwt, JWTError
    from app.core.security import SECRET_KEY, ALGORITHM, create_access_token, create_refresh_token
    
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing refresh token")
    token = auth_header.split(" ")[1]
    
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid token type")
        email = payload.get("sub")
        role_id = payload.get("role_id")
        if not email:
            raise HTTPException(status_code=401, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")
    
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    
    if not AuthService.check_user_active(user, db):
        raise HTTPException(status_code=403, detail="Account is inactive")
    
    new_access_token = create_access_token(data={"sub": email, "role_id": role_id})
    new_refresh_token = create_refresh_token(data={"sub": email, "role_id": role_id})
    
    return {
        "access_token": new_access_token,
        "refresh_token": new_refresh_token,
        "token_type": "bearer",
        "expires_in": 3600
>>>>>>> 62abb196b5fda5a4170358d520d80a96f76ab506
    }