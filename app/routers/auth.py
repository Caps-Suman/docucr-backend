from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from pydantic import BaseModel
import random
import string

from app.core.database import get_db
from app.models.user import User
from app.models.otp import OTP
from app.core.security import verify_password, create_access_token, get_password_hash
from app.utils.email import send_otp_email

router = APIRouter()

class LoginRequest(BaseModel):
    email: str
    password: str
    remember_me: bool = False

class ForgotPasswordRequest(BaseModel):
    email: str

class ResetPasswordRequest(BaseModel):
    email: str
    otp: str
    new_password: str

@router.post("/login")
async def login(request: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == request.email).first()
    if not user or not verify_password(request.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is inactive")

    expiry = timedelta(days=7) if request.remember_me else timedelta(minutes=30)
    access_token = create_access_token(
        data={"sub": user.email}, 
        expires_delta=expiry
    )
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": expiry.total_seconds(),
        "user": {
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name
        }
    }

@router.post("/forgot-password")
async def forgot_password(request: ForgotPasswordRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == request.email).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Generate OTP
    otp_code = ''.join(random.choices(string.digits, k=6))
    expires_at = datetime.utcnow() + timedelta(minutes=10)

    # Upsert OTP
    otp_record = db.query(OTP).filter(OTP.email == request.email).first()
    if otp_record:
        otp_record.otp_code = otp_code
        otp_record.expires_at = expires_at
        otp_record.is_used = False
    else:
        import uuid
        new_otp = OTP(
            id=str(uuid.uuid4()),
            email=request.email,
            otp_code=otp_code,
            expires_at=expires_at,
            is_used=False
        )
        db.add(new_otp)
    
    db.commit()

    # Send Email
    sent = send_otp_email(request.email, otp_code)
    if sent:
        return {"message": "OTP sent to your email"}
    else:
        raise HTTPException(status_code=500, detail="Failed to send email")

@router.post("/reset-password")
async def reset_password(request: ResetPasswordRequest, db: Session = Depends(get_db)):
    otp_record = db.query(OTP).filter(
        OTP.email == request.email, 
        OTP.otp_code == request.otp
    ).first()
    
    if not otp_record:
        raise HTTPException(status_code=400, detail="Invalid OTP")
    
    if otp_record.is_used:
        raise HTTPException(status_code=400, detail="OTP already used")

    if otp_record.expires_at < datetime.utcnow():
        raise HTTPException(status_code=400, detail="OTP expired")

    # Update Password
    user = db.query(User).filter(User.email == request.email).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    user.hashed_password = get_password_hash(request.new_password)
    otp_record.is_used = True
    
    db.commit()
    return {"message": "Password reset successfully"}