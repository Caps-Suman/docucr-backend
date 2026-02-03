from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..core.database import get_db
from ..core.security import get_current_user
from ..models.user import User
from ..models.role import Role
from ..models.user_role import UserRole
from ..models.status import Status
from ..services.dashboard_service import DashboardService

from app.core.permissions import Permission

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

@router.get("/admin")
def get_admin_dashboard(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    permission: bool = Depends(Permission("dashboard", "ADMIN"))
):
    """Get system-wide dashboard stats for admins"""
    return DashboardService.get_admin_stats(db)

@router.get("/user")
def get_user_dashboard(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    permission: bool = Depends(Permission("dashboard", "READ"))
):
    """Get user-specific dashboard stats"""
    return DashboardService.get_user_stats(db, current_user.id)
