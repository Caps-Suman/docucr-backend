from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List
from app.core.database import get_db
from app.core.security import get_current_user
from app.core.permissions import Permission
from app.services.document_share_service import DocumentShareService
from app.models.user import User
from ..services.activity_service import ActivityService
from fastapi import Request

router = APIRouter(prefix="/api/documents", tags=["document-sharing"], dependencies=[Depends(get_current_user)])

class ShareDocumentsRequest(BaseModel):
    document_ids: List[int]
    user_ids: List[str]

@router.post("/share")
async def share_documents(
    request: ShareDocumentsRequest,
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db),
    background_tasks: BackgroundTasks = None,
    permission: bool = Depends(Permission("documents", "SHARE")),
):
    service = DocumentShareService(db)

    created, users = service.share_documents(
        document_ids=request.document_ids,
        user_ids=request.user_ids,
        actor=current_user   # 🔥 PASS OBJECT
    )

    return {
        "message": "Documents shared successfully" if created else "Already shared",
        "new_shares": created
    }

@router.get("/shared-with-me")
async def get_shared_documents(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    permission: bool = Depends(Permission("documents", "READ"))
):
    """Get documents shared with current user"""
    service = DocumentShareService(db)
    return service.get_shared_documents(current_user.id)