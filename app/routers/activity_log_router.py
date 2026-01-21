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
    action: Optional[str] = None,
    entity_type: Optional[str] = None,
    user_id: Optional[str] = None,
    user_name: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    permission: bool = Depends(Permission("activity_log", "READ"))
) -> ActivityLogListResponse:
    """
    Get activity logs with pagination and filtering
    """
    query = db.query(ActivityLog)

    # Apply filters
    if action:
        query = query.filter(ActivityLog.action == action)
    if entity_type:
        query = query.filter(ActivityLog.entity_type == entity_type)
    if user_id:
        query = query.filter(ActivityLog.user_id == user_id)
    
    if user_name:
        query = query.join(User, ActivityLog.user_id == User.id).filter(
            (User.first_name.ilike(f"%{user_name}%")) | 
            (User.last_name.ilike(f"%{user_name}%")) | 
            (User.username.ilike(f"%{user_name}%")) | 
            (User.email.ilike(f"%{user_name}%"))
        )
    
    if start_date:
        query = query.filter(ActivityLog.created_at >= start_date)
    if end_date:
        query = query.filter(ActivityLog.created_at <= end_date)

    # Count total before pagination
    total = query.count()

    # Apply pagination and sorting
    query = query.order_by(desc(ActivityLog.created_at))
    query = query.offset((page - 1) * limit).limit(limit)
    
    # Eager load user
    query = query.options(joinedload(ActivityLog.user))
    
    logs = query.all()
    
    # Calculate total pages
    import math
    pages = math.ceil(total / limit) if limit > 0 else 0

    # Post-process to resolve entity names
    response_items = []
    
    # Collect IDs by entity type
    entity_ids_map = {}
    for log in logs:
        if log.entity_id and log.entity_type:
            if log.entity_type not in entity_ids_map:
                entity_ids_map[log.entity_type] = set()
            entity_ids_map[log.entity_type].add(log.entity_id)
            
    # Resolve names
    names_map = {}
    
    if "client" in entity_ids_map:
        clients = db.query(Client.id, Client.business_name, Client.first_name, Client.last_name).filter(Client.id.in_(entity_ids_map["client"])).all()
        for c in clients:
            name = c.business_name or f"{c.first_name} {c.last_name}".strip()
            names_map[f"client:{str(c.id)}"] = name
            
    if "user" in entity_ids_map:
        users = db.query(User.id, User.username, User.first_name, User.last_name).filter(User.id.in_(entity_ids_map["user"])).all()
        for u in users:
            name = f"{u.first_name} {u.last_name}".strip() if u.first_name else u.username
            names_map[f"user:{str(u.id)}"] = name
            
    if "role" in entity_ids_map:
        roles = db.query(Role.id, Role.name).filter(Role.id.in_(entity_ids_map["role"])).all()
        for r in roles:
            names_map[f"role:{str(r.id)}"] = r.name
            
    if "document" in entity_ids_map:
        # Filter out non-integer IDs for documents if any (safety check)
        doc_ids = [did for did in entity_ids_map["document"] if did.isdigit()]
        if doc_ids:
            docs = db.query(Document.id, Document.original_filename).filter(Document.id.in_(doc_ids)).all()
            for d in docs:
                names_map[f"document:{str(d.id)}"] = d.original_filename

    if "template" in entity_ids_map:
        temps = db.query(Template.id, Template.template_name).filter(Template.id.in_(entity_ids_map["template"])).all()
        for t in temps:
            names_map[f"template:{str(t.id)}"] = t.template_name

    if "form" in entity_ids_map:
        forms = db.query(Form.id, Form.name).filter(Form.id.in_(entity_ids_map["form"])).all()
        for f in forms:
            names_map[f"form:{str(f.id)}"] = f.name
            
    if "document_type" in entity_ids_map:
        dtypes = db.query(DocumentType.id, DocumentType.name).filter(DocumentType.id.in_(entity_ids_map["document_type"])).all()
        for dt in dtypes:
            names_map[f"document_type:{str(dt.id)}"] = dt.name
            
    if "printer" in entity_ids_map:
        printers = db.query(Printer.id, Printer.name).filter(Printer.id.in_(entity_ids_map["printer"])).all()
        for p in printers:
            names_map[f"printer:{str(p.id)}"] = p.name
            
    if "webhook" in entity_ids_map:
        # For webhook, name isn't standard, use URL or ID
        webhooks = db.query(Webhook.id, Webhook.url).filter(Webhook.id.in_(entity_ids_map["webhook"])).all()
        for w in webhooks:
            names_map[f"webhook:{str(w.id)}"] = w.url
                
    # Build response items
    for log in logs:
        item = ActivityLogResponse.model_validate(log)
        if log.entity_id and log.entity_type:
            key = f"{log.entity_type}:{str(log.entity_id)}"
            item.entity_name = names_map.get(key)
        response_items.append(item)

    return ActivityLogListResponse(
        items=response_items,
        total=total,
        page=page,
        limit=limit,
        pages=pages
    )
