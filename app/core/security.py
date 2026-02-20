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
        organisation_id = payload.get("organisation_id")

        if not email:
            raise HTTPException(401, "Invalid token")

    except JWTError:
        raise HTTPException(401, "Invalid token")

    user = db.query(User).filter(User.email == email).first()
    if user:
        user.is_org = False

        # 🔥 attach runtime context (DO NOT mutate DB fields)
        user.context_organisation_id = payload.get("organisation_id")
        user.context_is_superadmin = user.is_superuser and not organisation_id

        return user

    org = db.query(Organisation).filter(Organisation.email == email).first()
    if org:
        org.is_org = True
        return org

    raise HTTPException(401, "Not found")


def decode_token(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
    
def allow_temp_superadmin(
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    token = credentials.credentials
    payload = decode_token(token)

    # allow temp superadmin session
    if payload.get("temp") and payload.get("superadmin"):
        return payload

    raise HTTPException(403, "Superadmin temp session required")


def get_current_role_id(request: Request = None, credentials: HTTPAuthorizationCredentials = Depends(security)) -> Optional[str]:
    # We can get token from credentials
    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        role_id = payload.get("role_id")
        return role_id
    except JWTError:
        return None
