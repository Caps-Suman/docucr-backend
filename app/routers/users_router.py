from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
import re

from app.core.database import get_db
from app.services.user_service import UserService

router = APIRouter()

class UserCreate(BaseModel):
    email: str
    username: str = Field(..., min_length=3, max_length=50)
    first_name: str = Field(..., min_length=1, max_length=50)
    middle_name: Optional[str] = Field(None, max_length=50)
    last_name: str = Field(..., min_length=1, max_length=50)
    password: str = Field(..., min_length=6)
    phone_country_code: Optional[str] = None
    phone_number: Optional[str] = None
    role_ids: List[str] = []
    supervisor_id: Optional[str] = None
    client_id: Optional[str] = None
    
    @field_validator('email')
    @classmethod
    def validate_email(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError('Email cannot be empty')
        if not re.match(r'^[^\s@]+@[^\s@]+\.[^\s@]+$', v):
            raise ValueError('Invalid email format')
        return v.strip().lower()
    
    @field_validator('username')
    @classmethod
    def validate_username(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError('Username cannot be empty')
        return v.strip()

class UserUpdate(BaseModel):
    email: Optional[str] = None
    username: Optional[str] = Field(None, min_length=3, max_length=50)
    first_name: Optional[str] = Field(None, min_length=1, max_length=50)
    middle_name: Optional[str] = Field(None, max_length=50)
    last_name: Optional[str] = Field(None, min_length=1, max_length=50)
    phone_country_code: Optional[str] = None
    phone_number: Optional[str] = None
    status_id: Optional[str] = None
    role_ids: Optional[List[str]] = None
    supervisor_id: Optional[str] = None
    
    @field_validator('email')
    @classmethod
    def validate_email(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            if not v.strip():
                raise ValueError('Email cannot be empty')
            if not re.match(r'^[^\s@]+@[^\s@]+\.[^\s@]+$', v):
                raise ValueError('Invalid email format')
            return v.strip().lower()
        return v

class UserResponse(BaseModel):
    id: str
    email: str
    username: str
    first_name: Optional[str]
    middle_name: Optional[str]
    last_name: Optional[str]
    phone_country_code: Optional[str]
    phone_number: Optional[str]
    status_id: Optional[int]
    statusCode: Optional[str]
    is_superuser: bool
    roles: List[dict]
    supervisor_id: Optional[str]
    
    class Config:
        from_attributes = True

class UserListResponse(BaseModel):
    users: List[UserResponse]
    total: int
    page: int
    page_size: int

@router.get("", response_model=UserListResponse)
@router.get("/", response_model=UserListResponse)
async def get_users(
    page: int = 1,
    page_size: int = 10,
    search: Optional[str] = None,
    status_id: Optional[str] = None,
    db: Session = Depends(get_db)
):
    users, total = UserService.get_users(page, page_size, search, status_id, db)
    return UserListResponse(
        users=[UserResponse(**user) for user in users],
        total=total,
        page=page,
        page_size=page_size
    )

@router.get("/stats")
async def get_user_stats(db: Session = Depends(get_db)):
    return UserService.get_user_stats(db)

@router.get("/email/{email}", response_model=UserResponse)
async def get_user_by_email(email: str, db: Session = Depends(get_db)):
    user = UserService.get_user_by_email(email, db)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return UserResponse(**user)

@router.get("/{user_id}", response_model=UserResponse)
async def get_user(user_id: str, db: Session = Depends(get_db)):
    user = UserService.get_user_by_id(user_id, db)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return UserResponse(**user)

@router.post("/", response_model=UserResponse)
async def create_user(user: UserCreate, db: Session = Depends(get_db)):
    if UserService.check_email_exists(user.email, None, db):
        raise HTTPException(status_code=400, detail="Email already exists")
    if UserService.check_username_exists(user.username, None, db):
        raise HTTPException(status_code=400, detail="Username already exists")
    
    user_data = user.model_dump()
    created_user = UserService.create_user(user_data, db)
    return UserResponse(**created_user)

@router.put("/{user_id}", response_model=UserResponse)
async def update_user(user_id: str, user: UserUpdate, db: Session = Depends(get_db)):
    if user.email and UserService.check_email_exists(user.email, user_id, db):
        raise HTTPException(status_code=400, detail="Email already exists")
    if user.username and UserService.check_username_exists(user.username, user_id, db):
        raise HTTPException(status_code=400, detail="Username already exists")
    if user.phone_number:
        if not user.phone_number.isdigit():
            raise HTTPException(status_code=400, detail="Phone number must contain only digits")
        if len(user.phone_number) < 10 or len(user.phone_number) > 15:
            raise HTTPException(status_code=400, detail="Phone number must be 10-15 digits")
    
    user_data = user.model_dump(exclude_unset=True)
    updated_user = UserService.update_user(user_id, user_data, db)
    if not updated_user:
        raise HTTPException(status_code=404, detail="User not found")
    return UserResponse(**updated_user)

@router.post("/{user_id}/activate", response_model=UserResponse)
async def activate_user(user_id: str, db: Session = Depends(get_db)):
    user = UserService.activate_user(user_id, db)
    if not user:
        raise HTTPException(status_code=400, detail="Cannot activate user")
    return UserResponse(**user)

@router.post("/{user_id}/deactivate", response_model=UserResponse)
async def deactivate_user(user_id: str, db: Session = Depends(get_db)):
    user = UserService.deactivate_user(user_id, db)
    if not user:
        raise HTTPException(status_code=400, detail="Cannot deactivate user")
    return UserResponse(**user)
