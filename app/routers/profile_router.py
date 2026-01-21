from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.services.profile_service import ProfileService
from app.services.activity_service import ActivityService
from app.core.permissions import Permission

router = APIRouter()

class ProfileUpdateRequest(BaseModel):
    first_name: Optional[str] = None
    middle_name: Optional[str] = None
    last_name: Optional[str] = None
    username: Optional[str] = None
    phone_country_code: Optional[str] = None
    phone_number: Optional[str] = None

class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str

@router.get("/me")
async def get_profile(
    current_user: User = Depends(get_current_user),
    permission: bool = Depends(Permission("profile", "READ"))
):
    return ProfileService.get_profile(current_user)

@router.put("/me")
async def update_profile(
    request: ProfileUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    permission: bool = Depends(Permission("profile", "UPDATE")),
    req: Request = None,
    background_tasks: BackgroundTasks = None
):
    if request.username and ProfileService.check_username_exists(request.username, current_user.id, db):
        raise HTTPException(status_code=400, detail="Username already exists")
    if request.phone_number:
        if not request.phone_number.isdigit():
            raise HTTPException(status_code=400, detail="Phone number must contain only digits")
        if len(request.phone_number) < 10 or len(request.phone_number) > 15:
            raise HTTPException(status_code=400, detail="Phone number must be 10-15 digits")
    
    profile_data = request.model_dump(exclude_unset=True)
    
    # Calculate changes
    changes = ActivityService.calculate_changes(current_user, profile_data, exclude=["password", "hashed_password"])
    
    ProfileService.update_profile(current_user, profile_data, db)
    
    ActivityService.log(
        db,
        action="UPDATE",
        entity_type="user",
        entity_id=current_user.id,
        user_id=current_user.id,
        details={"changes": changes},
        request=req,
        background_tasks=background_tasks
    )
    
    return {"message": "Profile updated successfully"}

@router.post("/change-password")
async def change_password(
    request: PasswordChangeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    permission: bool = Depends(Permission("profile", "UPDATE")),
    req: Request = None,
    background_tasks: BackgroundTasks = None
):
    if not ProfileService.change_password(current_user, request.current_password, request.new_password, db):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    
    ActivityService.log(
        db,
        action="UPDATE",
        entity_type="user",
        entity_id=current_user.id,
        user_id=current_user.id,
        details={"sub_action": "CHANGE_PASSWORD"},
        request=req,
        background_tasks=background_tasks
    )
    
    return {"message": "Password changed successfully"}
