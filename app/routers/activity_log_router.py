from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc, or_
from typing import List, Optional, Any, Dict
from sqlalchemy.orm import Session, joinedload
from pydantic import BaseModel
from datetime import datetime

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.permissions import Permission
from app.models.activity_log import ActivityLog
from app.models.user import User

from app.models.user import User
from app.models.activity_log import ActivityLog
from app.models.client import Client
from app.models.role import Role
from app.models.document import Document
from app.models.document_type import DocumentType
from app.models.form import Form
from app.models.template import Template
from app.models.printer import Printer
from app.models.webhook import Webhook

router = APIRouter(prefix="/api/activity-logs", tags=["activity-logs"])

class UserSummary(BaseModel):
    id: str
    username: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None

    class Config:
        from_attributes = True

class ActivityLogResponse(BaseModel):
    id: Any
    action: str
    entity_type: str
    entity_id: Optional[str] = None
    entity_name: Optional[str] = None
    user_id: Optional[str] = None
    user: Optional[UserSummary] = None
    details: Optional[Dict[str, Any]] = None
    ip_address: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True

class ActivityLogListResponse(BaseModel):
    items: List[ActivityLogResponse]
    total: int
    page: int
    limit: int
    pages: int

@router.get("/")
async def get_activity_logs(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    entity_id: Optional[str] = Query(None, description="Entity ID (e.g. Document ID)"),
    entity_type: Optional[str] = Query(None, description="Entity Type (e.g. 'document')"),
    action: Optional[str] = None,
    user_id: Optional[str] = None,
    user_name: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get activity logs with pagination and filtering.
    """
    from app.services.activity_service import ActivityService
    
    result = ActivityService.get_activity_logs(
        db=db,
        entity_id=entity_id,
        entity_type=entity_type,
        action=action,
        user_name=user_name,
        start_date=start_date,
        limit=limit,
        offset=(page - 1) * limit
    )
    
    import math
    total = result["total"]
    pages = math.ceil(total / limit) if limit > 0 else 0

    return {
        "items": result["items"],
        "total": total,
        "page": page,
        "limit": limit,
        "pages": pages
    }
