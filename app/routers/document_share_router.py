from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List
from app.core.database import get_db
from app.core.security import get_current_user
from app.services.document_share_service import DocumentShareService
from app.models.user import User

router = APIRouter(prefix="/api/documents", tags=["document-sharing"], dependencies=[Depends(get_current_user)])

class ShareDocumentsRequest(BaseModel):
    document_ids: List[int]
    user_ids: List[str]

@router.post("/share")
async def share_documents(
    request: ShareDocumentsRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Share documents with users"""
    service = DocumentShareService(db)
    service.share_documents(request.document_ids, request.user_ids, current_user.id)
    return {"message": "Documents shared successfully"}

@router.get("/shared-with-me")
async def get_shared_documents(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get documents shared with current user"""
    service = DocumentShareService(db)
    return service.get_shared_documents(current_user.id)