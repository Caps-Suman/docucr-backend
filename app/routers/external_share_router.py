from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr
from typing import List, Optional

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.permissions import Permission
from app.models.user import User
from app.services.external_share_service import ExternalShareService

router = APIRouter(tags=["external-sharing"])

# --- Schemas ---

class CreateExternalShareRequest(BaseModel):
    document_id: int
    email: EmailStr
    password: str
    expires_in_days: Optional[int] = 7

class CreateBatchExternalShareRequest(BaseModel):
    document_ids: List[int]
    email: EmailStr
    password: str
    expires_in_days: Optional[int] = 7

class VerifyShareRequest(BaseModel):
    password: str

# --- Protected Endpoints ---

@router.post("/api/documents/share/external")
async def create_external_share(
    request: CreateExternalShareRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    permission: bool = Depends(Permission("documents", "SHARE"))
):
    """Create a password-protected share link for an external user."""
    service = ExternalShareService(db)
    share = service.create_share(
        document_id=request.document_id,
        email=request.email,
        password=request.password,
        shared_by=current_user.id,
        expires_in_days=request.expires_in_days
    )
    return {
        "message": "External share created successfully",
        "token": share.token,
        "expires_at": share.expires_at.isoformat()
    }

@router.post("/api/documents/share/external/batch")
async def create_external_share_batch(
    request: CreateBatchExternalShareRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    permission: bool = Depends(Permission("documents", "SHARE"))
):
    """Create multiple password-protected share links and send ONE email."""
    service = ExternalShareService(db)
    shares = service.create_batch_share(
        document_ids=request.document_ids,
        email=request.email,
        password=request.password,
        shared_by=current_user.id,
        expires_in_days=request.expires_in_days
    )
    return {
        "message": f"Successfully created {len(shares)} share links",
        "shares": [
            {"document_id": s.document_id, "token": s.token} for s in shares
        ]
    }

# --- Public Endpoints ---

@router.get("/api/public/shares/{token}")
async def get_share_metadata(token: str, db: Session = Depends(get_db)):
    """Get public metadata for a share token (filename, etc.) before authentication."""
    service = ExternalShareService(db)
    share = service.get_share_by_token(token)
    return {
        "filename": share.document.filename,
        "shared_by": f"{share.shared_by_user.first_name} {share.shared_by_user.last_name}",
        "expires_at": share.expires_at.isoformat()
    }

@router.post("/api/public/shares/{token}/verify")
async def verify_external_share(
    token: str, 
    request: VerifyShareRequest, 
    db: Session = Depends(get_db)
):
    """Verify password and return document data."""
    service = ExternalShareService(db)
    doc_data = service.get_shared_document_data(token, request.password)
    return doc_data
