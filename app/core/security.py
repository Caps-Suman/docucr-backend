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

# def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security), db: Session = Depends(get_db)):
#     token = credentials.credentials
#     try:
#         payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
#         if payload.get("type") != "access":
#             raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")
#         email: str = payload.get("sub")
#         if email is None:
#             raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
#     except JWTError:
#         raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    
#     user = db.query(User).filter(User.email == email).first()
#     if user is None:
#         # Fallback to Organisation
#         org = db.query(Organisation).filter(Organisation.email == email).first()
#         if org is None:
#             raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
#         return org
    
#     return user
def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
):
    token = credentials.credentials

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])

        if payload.get("type") != "access":
            raise HTTPException(status_code=401, detail="Invalid token type")

        email = payload.get("sub")
        if not email:
            raise HTTPException(status_code=401, detail="Invalid token")

    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    # ---- try USER first ----
    user = db.query(User).filter(User.email == email).first()
    if user:
        user.is_org = False
        return user

    org = db.query(Organisation).filter(Organisation.email == email).first()
    if org:
        org.is_org = True
        return org

    raise HTTPException(401, "Not found")

    # 🔴 IMPORTANT: convert organisation → pseudo user
    class OrgWrapper:
        def __init__(self, org):
            self.id = org.id
            self.organisation_id = org.id
            self.email = org.email
            self.is_superuser = org.is_superuser
            self.roles = org.roles
            self.is_org = True

    return OrgWrapper(org)

def get_current_role_id(request: Request = None, credentials: HTTPAuthorizationCredentials = Depends(security)) -> Optional[str]:
    # We can get token from credentials
    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        role_id = payload.get("role_id")
        return role_id
    except JWTError:
        return None
