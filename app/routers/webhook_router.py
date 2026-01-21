from fastapi import APIRouter, Depends, HTTPException, Request, BackgroundTasks
from app.services.activity_service import ActivityService
from sqlalchemy.orm import Session
from typing import List
from ..core.database import get_db
from ..core.security import get_current_user
from ..core.permissions import Permission
from ..models.user import User
from ..services.webhook_service import webhook_service

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])

@router.get("/")
async def get_webhooks(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    permission: bool = Depends(Permission("profile", "UPDATE"))
):
    """List all webhooks for the current user"""
    return webhook_service.get_user_webhooks(db, current_user.id)

@router.post("/")
async def create_webhook(
    data: dict,
    request: Request,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    permission: bool = Depends(Permission("profile", "UPDATE"))
):
    """Create a new webhook"""
    webhook = webhook_service.create_webhook(db, current_user.id, data)
    
    ActivityService.log(
        db=db,
        action="CREATE",
        entity_type="webhook",
        entity_id=webhook.id,
        user_id=current_user.id,
        details={"url": webhook.url, "events": webhook.events},
        request=request,
        background_tasks=background_tasks
    )
    
    return webhook

@router.patch("/{webhook_id}")
async def update_webhook(
    webhook_id: str,
    data: dict,
    request: Request,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    permission: bool = Depends(Permission("profile", "UPDATE"))
):
    """Update a webhook configuration"""
    webhook = webhook_service.update_webhook(db, webhook_id, current_user.id, data)
    if not webhook:
        raise HTTPException(status_code=404, detail="Webhook not found")
        
    ActivityService.log(
        db=db,
        action="UPDATE",
        entity_type="webhook",
        entity_id=webhook_id,
        user_id=current_user.id,
        details={"updated_fields": list(data.keys())},
        request=request,
        background_tasks=background_tasks
    )
    
    return webhook

@router.delete("/{webhook_id}")
async def delete_webhook(
    webhook_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    permission: bool = Depends(Permission("profile", "UPDATE"))
):
    """Delete a webhook"""
    success = webhook_service.delete_webhook(db, webhook_id, current_user.id)
    if not success:
        raise HTTPException(status_code=404, detail="Webhook not found")
        
    ActivityService.log(
        db=db,
        action="DELETE",
        entity_type="webhook",
        entity_id=webhook_id,
        user_id=current_user.id,
        request=request,
        background_tasks=background_tasks
    )
    
    return {"message": "Webhook deleted"}
