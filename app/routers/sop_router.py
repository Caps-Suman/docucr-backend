from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import List, Optional, Any, Dict
from pydantic import BaseModel
from uuid import UUID
import io

from app.core.database import get_db
from app.services.sop_service import SOPService
from app.core.security import get_current_user
# Assuming generic permissions or skipping for now as per "simple integration" request, but better to be safe.
# Using generic "sops" permission resource name based on patterns.
from app.core.permissions import Permission

router = APIRouter()

# --- Schemas ---
# Defining schemas here for simplicity as per user request to "integrate". 
# If a separate schemas file is preferred, I can move it, but keeping it co-located is often easier for initial iteration.
# Actually, I should check if there is a schemas directory. Previous list_dir showed no schemas dir?
# Ah, list_dir returned "directory ... does not exist". 
# So schemas are likely inside routers or models or separate files? 
# Clients router defined models inline. I will do the same.

class SOPBase(BaseModel):
    title: str
    category: str
    provider_type: str
    client_id: Optional[UUID] = None
    provider_info: Optional[Dict[str, Any]] = None
    workflow_process: Optional[Dict[str, Any]] = None
    billing_guidelines: Optional[List[Dict[str, Any]]] = None
    coding_rules: Optional[List[Dict[str, Any]]] = None
    status_id: Optional[int] = None

class SOPCreate(SOPBase):
    pass

class SOPUpdate(SOPBase):
    pass

class SOPStatusUpdate(BaseModel):
    status_id: int

class StatusInfo(BaseModel):
    id: int
    code: str
    description: Optional[str] = None
    
    class Config:
        from_attributes = True

class SOPShortResponse(BaseModel):
    id: UUID
    title: str
    category: str
    provider_info: Optional[Dict[str, Any]] = None
    status_id: Optional[int] = None
    status: Optional[StatusInfo] = None
    updated_at: Any

    class Config:
        from_attributes = True

class SOPResponse(SOPBase):
    id: UUID
    status: Optional[StatusInfo] = None
    created_at: Any
    updated_at: Any

    class Config:
        from_attributes = True

class SOPListResponse(BaseModel):
    sops: List[SOPShortResponse]
    total: int

# --- Endpoints ---

@router.post("", response_model=SOPResponse, status_code=status.HTTP_201_CREATED)
def create_sop(
    sop: SOPCreate, 
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    return SOPService.create_sop(sop.model_dump(), db)

@router.get("", response_model=SOPListResponse)
def get_sops(
    skip: int = 0, 
    limit: int = 100, 
    search: Optional[str] = None,
    status_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    sops, total = SOPService.get_sops(db, skip=skip, limit=limit, search=search, status_id=status_id)
    return {"sops": sops, "total": total}

@router.get("/{sop_id}", response_model=SOPResponse)
def get_sop(
    sop_id: str, 
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    sop = SOPService.get_sop_by_id(sop_id, db)
    if not sop:
        raise HTTPException(status_code=404, detail="SOP not found")
    return sop

@router.put("/{sop_id}", response_model=SOPResponse)
def update_sop(
    sop_id: str, 
    sop: SOPUpdate, 
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    updated_sop = SOPService.update_sop(sop_id, sop.model_dump(), db)
    if not updated_sop:
        raise HTTPException(status_code=404, detail="SOP not found")
    return updated_sop

@router.patch("/{sop_id}", response_model=SOPResponse)
def update_sop_status(
    sop_id: str,
    status_update: SOPStatusUpdate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    updated_sop = SOPService.update_sop(sop_id, status_update.model_dump(), db)
    if not updated_sop:
        raise HTTPException(status_code=404, detail="SOP not found")
    return updated_sop

@router.delete("/{sop_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_sop(
    sop_id: str, 
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    success = SOPService.delete_sop(sop_id, db)
    if not success:
        raise HTTPException(status_code=404, detail="SOP not found")
    return None

@router.get("/{sop_id}/pdf")
def download_sop_pdf(
    sop_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    sop = SOPService.get_sop_by_id(sop_id, db)
    if not sop:
        raise HTTPException(status_code=404, detail="SOP not found")
    
    pdf_buffer = SOPService.generate_sop_pdf(sop)
    return StreamingResponse(
        io.BytesIO(pdf_buffer),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={sop.title.replace(' ', '_')}.pdf"}
    )
