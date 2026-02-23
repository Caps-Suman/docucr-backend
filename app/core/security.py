from passlib.context import CryptContext
from jose import JWTError, jwt
from datetime import datetime, timedelta
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from typing import Optional
import os

from app.core.database import get_db
from app.models.user import User
from app.models.organisation import Organisation

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()

SECRET_KEY = os.getenv("JWT_SECRET_KEY", "your-secret-key")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60  # 1 hour
REFRESH_TOKEN_EXPIRE_HOURS = 24  # 24 hours

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def create_refresh_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(hours=REFRESH_TOKEN_EXPIRE_HOURS)
    to_encode.update({"exp": expire, "type": "refresh"})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
):
    token = credentials.credentials

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        print("TOKEN PAYLOAD:", payload)

        if payload.get("type") != "access":
            raise HTTPException(401, "Invalid token type")

        email = payload.get("sub")
        if not email:
            raise HTTPException(401, "Invalid token")

    except JWTError:
        raise HTTPException(401, "Invalid token")

    # =========================================
    # 1️⃣ TEMP SUPERADMIN (before org select)
    # =========================================
    if payload.get("temp") and payload.get("superadmin"):
        user = db.query(User).filter(User.email == email).first()
        if not user:
            raise HTTPException(401, "User not found")

        user.context_organisation_id = None
        user.context_role_id = None
        user.context_is_superadmin = True
        user.context_temp = True

        return user

    # =========================================
    # 2️⃣ NORMAL ORG CONTEXT LOGIN
    # =========================================
    organisation_id = payload.get("organisation_id")
    role_id = payload.get("role_id")

    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(401, "User not found")

    # attach runtime context
    user.context_organisation_id = organisation_id
    user.context_role_id = role_id
    user.context_is_superadmin = user.is_superuser
    user.context_temp = False
    return user

def decode_token(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
    
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from app.core.security import security, decode_token

def allow_temp_superadmin(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    payload = decode_token(credentials.credentials)

    if not payload.get("temp") or not payload.get("superadmin"):
        raise HTTPException(status_code=403, detail="Not temp superadmin")

    return payload


def get_current_role_id(request: Request = None, credentials: HTTPAuthorizationCredentials = Depends(security)) -> Optional[str]:
    # We can get token from credentials
    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        role_id = payload.get("role_id")
        return role_id
    except JWTError:
        return None
