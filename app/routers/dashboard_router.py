from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..core.database import get_db
from ..core.security import get_current_user
from ..models.user import User
from ..models.role import Role
from ..models.user_role import UserRole
from ..models.status import Status
from ..services.dashboard_service import DashboardService

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

def check_admin_access(current_user: User, db: Session):
    user_roles = db.query(Role.name).join(UserRole).join(User).filter(
        User.id == current_user.id,
        Role.status_id.in_(
            db.query(Status.id).filter(Status.code == 'ACTIVE')
        )
    ).all()
    
    role_names = [role.name for role in user_roles]
    if not any(role in ['ADMIN', 'SUPER_ADMIN'] for role in role_names):
        raise HTTPException(status_code=403, detail="Admin access required")

@router.get("/admin")
async def get_admin_dashboard(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get system-wide dashboard stats for admins"""
    check_admin_access(current_user, db)
    return DashboardService.get_admin_stats(db)

@router.get("/user")
async def get_user_dashboard(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get user-specific dashboard stats"""
    return DashboardService.get_user_stats(db, current_user.id)
