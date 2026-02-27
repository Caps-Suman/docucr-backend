from fastapi import APIRouter, HTTPException, Depends, Request, BackgroundTasks
from sqlalchemy.orm import Session
from datetime import timedelta
from pydantic import BaseModel
from typing import Optional

from app.core.database import get_db
from app.core.security import get_current_user
from app.models import user
from app.models import user, OTP
from app.services.auth_service import AuthService
from app.services.activity_service import ActivityService
from app.models.user import User
from app.services.organisations_service import OrganisationService

router = APIRouter()

class LoginRequest(BaseModel):
    email: str
    password: str
    remember_me: bool = False

class RoleSelectionRequest(BaseModel):
    email: str
    role_id: str
    organisation_id: str
    remember_me: bool = False

class ForgotPasswordRequest(BaseModel):
    email: str

class ResetPasswordRequest(BaseModel):
    email: str
    otp: str
    new_password: str

class TwoFactorRequest(BaseModel):
    email: str
    otp: str

# @router.post("/login")
# async def login(
#     request: LoginRequest, req: Request, background_tasks: BackgroundTasks, db: Session = Depends(get_db),
#     page: int = 1,
#     page_size: int = 10,
#     search: Optional[str] = None,
#     status_id: Optional[str] = None,
#     ):
#     user = AuthService.authenticate_user(request.email, request.password, db)
    
#     if not user:
#         # Fallback: Try Organisation Login
#         org = AuthService.authenticate_organisation(request.email, request.password, db)
#         if not org:
#             # Optional: Log failed login attempt
#             ActivityService.log(
#                 db, 
#                 action="LOGIN_FAILED", 
#                 entity_type="user", 
#                 details={"email": request.email}, 
#                 request=req,
#                 background_tasks=background_tasks
#             )
#             raise HTTPException(status_code=401, detail="Invalid credentials")
        
#         if not AuthService.check_organisation_active(org, db):
#             raise HTTPException(status_code=403, detail="Account is inactive")
        
#         roles = AuthService.get_organisation_roles(org.id, db)
#         if not roles:
#             raise HTTPException(status_code=403, detail="No active roles assigned")

#         ActivityService.log(
#              db,
#              action="LOGIN",
#              entity_type="organisation",
#              entity_id=org.id,
#              request=req,
#              background_tasks=background_tasks
#         )

#         # Organisation always has one role context usually, logic similar to single role user
#         # Assuming organisations don't have client mapping logic for now or it's different
        
#         tokens = AuthService.generate_tokens(org.email, roles[0]["id"])
#         permissions = AuthService.get_role_permissions(roles[0]["id"], db)

#         return {
#             **tokens,
#             "user": {
#                 "id": org.id,
#                 "email": org.email,
#                 "first_name": org.first_name,
#                 "last_name": org.last_name,
#                 "role": roles[0],
#                 "is_client": False, # Organisations aren't clients in this context
#                 "client_id": None,
#                 "client_name": None,
#                 "permissions": permissions,
#                 "profile_image_url": getattr(org, 'profile_image_url', None)
#             }
#         }
    
#     if not AuthService.check_user_active(user, db):
#         raise HTTPException(status_code=403, detail="Account is inactive")
#     # SUPERADMIN FLOW
#     if user.is_superuser:
#         from app.core.security import create_access_token

#         temp_token = create_access_token(
#             data={
#                 "sub": user.email,
#                 "temp": True,
#                 "superadmin": True
#             },
#             expires_delta=timedelta(minutes=15)
#         )

#         orgs, total = OrganisationService.get_organisations(page, page_size, search, status_id, db)

#         return {
#             "requires_org_selection": True,
#             "temp_token": temp_token,
#             "organisations": orgs,
#             "total": total,
#             "user": {
#                 "id": user.id,
#                 "email": user.email,
#                 "first_name": user.first_name,
#                 "last_name": user.last_name
#             }
#         }


#     # Check for 2FA - Compulsory for all except Super Admins
#     if not user.is_superuser:
#         if AuthService.initiate_2fa(user.email, db):
#             return {
#                 "requires_2fa": True,
#                 "message": "2FA code sent to your email",
#                 "profile_image_url": user.profile_image_url
#             }
#         else:
#             raise HTTPException(status_code=500, detail="Failed to send 2FA code")

#     ActivityService.log(
#         db,
#         action="LOGIN",
#         entity_type="user",
#         entity_id=user.id,
#         user_id=user.id,
#         request=req,
#         background_tasks=background_tasks
#     )

#     roles = AuthService.get_user_roles(user.id, db)
    
#     if not roles:
#         raise HTTPException(status_code=403, detail="No active roles assigned")
    
#     if len(roles) == 1:
#         tokens = AuthService.generate_tokens(user.email, roles[0]["id"])
#         permissions = AuthService.get_role_permissions(roles[0]["id"], db)
#         client = None
#         client_name = None

#         if user.is_client and user.client_id:
#             client = AuthService.get_client_by_id(user.client_id, db)
#             if client:
#                 client_name = (
#                     client.business_name
#                     or f"{client.first_name} {client.last_name}".strip()
#                 )

#         return {
#             **tokens,
#             "user": {
#                 "id": user.id,
#                 "email": user.email,
#                 "first_name": user.first_name,
#                 "last_name": user.last_name,
#                 "role": roles[0],
#                 "is_client": user.is_client,
#                 "client_id": user.client_id,
#                 "client_name": client_name,
#                 "permissions": permissions,
#                 "profile_image_url": user.profile_image_url
#             }
#         }
    
#     from app.core.security import create_access_token
#     temp_token = create_access_token(data={"sub": user.email, "temp": True}, expires_delta=timedelta(minutes=5))
    
#     return {
#         "requires_role_selection": True,
#         "temp_token": temp_token,
#         "roles": roles,
#         "user": {
#             "id": user.id,
#             "email": user.email,
#             "first_name": user.first_name,
#             "last_name": user.last_name
#         }
#     }

@router.post("/login")
async def login(
    request: LoginRequest,
    req: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
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
        raise HTTPException(401, "Invalid credentials")

    # This will raise specific HTTPException if inactive (User or Org)
    AuthService.check_user_active(user, db)

    # 🔥 SUPERADMIN FLOW (global)
    if user.is_superuser:
        from app.core.security import create_access_token

        temp_token = create_access_token(
            data={
                "sub": user.email,
                "temp": True,
                "superadmin": True
            },
            expires_delta=timedelta(minutes=15)
        )

        return {
            "requires_org_selection": True,
            "temp_token": temp_token,
            "user": {
                "id": user.id,
                "email": user.email,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "is_superuser": True
            }
        }

    # 🔥 2FA FLOW
    if AuthService.initiate_2fa(user.email, db):
        return {
            "requires_2fa": True,
            "message": "2FA code sent",
            "profile_image_url": user.profile_image_url
        }

    raise HTTPException(500, "Failed to send 2FA")


@router.post("/select-role")
async def select_role(request: RoleSelectionRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if current_user.email != request.email:
        raise HTTPException(status_code=403, detail="Unauthorized to select role for this user")
    
    AuthService.check_user_active(current_user, db)
    
    role = AuthService.verify_user_role(current_user.id, request.role_id, db)
    if not role:
        raise HTTPException(status_code=403, detail="User does not have this role")

    tokens = AuthService.generate_tokens(current_user.email, request.role_id, request.organisation_id, is_superadmin=current_user.is_superuser)
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
            "is_superuser": current_user.is_superuser,
            "is_client": current_user.is_client,
            "client_id": current_user.client_id,
            "client_name": client_name,
            "permissions": permissions,
            "profile_image_url": current_user.profile_image_url
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

    otp_code = AuthService.generate_otp(request.email, db, purpose="RESET")
    sent = send_otp_email(request.email, otp_code, purpose="RESET")
    
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
    if not AuthService.verify_otp(request.email, request.otp, db, purpose="RESET"):
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

@router.post("/verify-2fa")
async def verify_2fa(request: TwoFactorRequest, db: Session = Depends(get_db)):
    if not AuthService.verify_otp(request.email, request.otp, db, purpose="LOGIN"):
        raise HTTPException(status_code=400, detail="Invalid or expired 2FA code")
    
    user = db.query(User).filter(User.email == request.email).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Mark OTP as used
    otp_record = db.query(OTP).filter(OTP.email == request.email, OTP.otp_code == request.otp, OTP.purpose == "LOGIN").first()
    if otp_record:
        otp_record.is_used = True
        db.commit()

    roles = AuthService.get_user_roles(user.id, db)
    if not roles:
        raise HTTPException(status_code=403, detail="No active roles assigned")
    
    if len(roles) == 1:
        tokens = AuthService.generate_tokens(
            email=user.email,
            role_id=roles[0]["id"],
            organisation_id=user.organisation_id
        )
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
                "is_superuser": user.is_superuser,
                "is_client": user.is_client,
                "client_id": user.client_id,
                "client_name": client_name,
                "permissions": permissions,
                "profile_image_url": user.profile_image_url
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
            "last_name": user.last_name,
            "is_superuser": user.is_superuser
        }
    }

@router.post("/resend-2fa")
async def resend_2fa(request: LoginRequest, db: Session = Depends(get_db)):
    # Note: Using LoginRequest because resend-2fa doesn't need password but frontend might send it or just email
    user = db.query(User).filter(User.email == request.email).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    if AuthService.initiate_2fa(request.email, db):
        return {"message": "2FA code resent to your email"}
    else:
        raise HTTPException(status_code=500, detail="Failed to send 2FA code")

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
    
    AuthService.check_user_active(user, db)

    organisation_id = payload.get("organisation_id")
    is_superadmin = payload.get("superadmin", False)

    if not role_id or not organisation_id:
        raise HTTPException(401, "Invalid refresh context")

    data = {
        "sub": email,
        "role_id": role_id,
        "organisation_id": organisation_id
    }
    if is_superadmin:
        data["superadmin"] = True

    new_access_token = create_access_token(data)
    new_refresh_token = create_refresh_token(data=data)
    
    return {
        "access_token": new_access_token,
        "refresh_token": new_refresh_token,
        "token_type": "bearer",
        "expires_in": 3600
    }