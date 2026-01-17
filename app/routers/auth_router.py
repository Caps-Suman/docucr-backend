from fastapi import APIRouter, HTTPException, Depends, Request
from sqlalchemy.orm import Session
from datetime import timedelta
from pydantic import BaseModel
from typing import Optional

from app.core.database import get_db
from app.core.security import get_current_user
from app.services.auth_service import AuthService
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
async def login(request: LoginRequest, db: Session = Depends(get_db)):
    user = AuthService.authenticate_user(request.email, request.password, db)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    if not AuthService.check_user_active(user, db):
        raise HTTPException(status_code=403, detail="Account is inactive")

    roles = AuthService.get_user_roles(user.id, db)
    
    if len(roles) == 1:
        tokens = AuthService.generate_tokens(user.email, roles[0]["id"])
        return {
            **tokens,
            "user": {
                "id": user.id,
                "email": user.email,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "role": roles[0]
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
    
    return {
        **tokens,
        "user": {
            "id": current_user.id,
            "email": current_user.email,
            "first_name": current_user.first_name,
            "last_name": current_user.last_name,
            "role": {"id": role.id, "name": role.name}
        }
    }

@router.post("/forgot-password")
async def forgot_password(request: ForgotPasswordRequest, db: Session = Depends(get_db)):
    from app.services.user_service import UserService
    from app.utils.email import send_otp_email
    
    user = UserService.get_user_by_email(request.email, db)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    otp_code = AuthService.generate_otp(request.email, db)
    sent = send_otp_email(request.email, otp_code)
    
    if sent:
        return {"message": "OTP sent to your email"}
    else:
        raise HTTPException(status_code=500, detail="Failed to send email")

@router.post("/reset-password")
async def reset_password(request: ResetPasswordRequest, db: Session = Depends(get_db)):
    if not AuthService.verify_otp(request.email, request.otp, db):
        raise HTTPException(status_code=400, detail="Invalid or expired OTP")
    
    if not AuthService.reset_user_password(request.email, request.otp, request.new_password, db):
        raise HTTPException(status_code=404, detail="User not found")
    
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
    
    new_access_token = create_access_token(data={"sub": email, "role_id": role_id})
    new_refresh_token = create_refresh_token(data={"sub": email, "role_id": role_id})
    
    return {
        "access_token": new_access_token,
        "refresh_token": new_refresh_token,
        "token_type": "bearer",
        "expires_in": 3600
    }