import os
import tempfile
import uuid
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import List, Optional, Any, Dict
from pydantic import BaseModel
from uuid import UUID
import io

from app.core.database import get_db
from app.models.user import User
from app.services.ai_sop_service import AISOPService
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

class BillingRule(BaseModel):
    description: str

class BillingGuidelineGroup(BaseModel):
    category: str
    rules: list[BillingRule]


class PayerGuideline(BaseModel):
    payer_name:str
    description:str
class SOPBase(BaseModel):
    title: str
    category: str
    provider_type: str
    client_id: Optional[UUID] = None
    provider_info: Optional[Dict[str, Any]] = None
    workflow_process: Optional[Dict[str, Any]] = None
    # billing_guidelines: Optional[List[Dict[str, Any]]] = None
    billing_guidelines: Optional[List[BillingGuidelineGroup]]=None
    payer_guidelines: Optional[List[PayerGuideline]]=None
    coding_rules_cpt: Optional[List[Dict[str, Any]]] = None
    coding_rules_icd: Optional[List[Dict[str, Any]]] = None
    status_id: Optional[int] = None
    created_by: Optional[str] = None
    organisation_id: Optional[str] = None

class SOPCreate(SOPBase):
    provider_ids: Optional[List[UUID]] = []

class SOPUpdate(SOPBase):
    provider_ids: Optional[List[UUID]] = None

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
    created_by: Optional[str] = None
    created_by_name: Optional[str] = None
    organisation_id: Optional[str] = None
    organisation_name: Optional[str] = None
    client_id: Optional[UUID] = None
    client_name: Optional[str] = None
    client_npi: Optional[str] = None
    updated_at: Any

    class Config:
        from_attributes = True

class SOPStatsResponse(BaseModel):
    total_sops: int
    active_sops: int
    inactive_sops: int

class SOPResponse(SOPBase):
    id: UUID
    status: Optional[StatusInfo] = None
    created_by_name: Optional[str] = None
    organisation_name: Optional[str] = None
    client_name: Optional[str] = None
    client_npi: Optional[str] = None
    created_at: Any
    updated_at: Any
    providers: Optional[List[Dict[str, Any]]] = None

    class Config:
        from_attributes = True

class SOPListResponse(BaseModel):
    sops: List[SOPShortResponse]
    total: int
class AISOPExtractResponse(BaseModel):
    source_file: str
    extracted_data: Dict[str, Any]

# --- Endpoints ---

@router.post("", response_model=SOPResponse, status_code=status.HTTP_201_CREATED)
def create_sop(
    sop: SOPCreate, 
    db: Session = Depends(get_db),
    current_user: Any = Depends(Permission("SOPS", "CREATE"))
):
    sop_data = sop.model_dump()
    return SOPService.create_sop(sop_data, db, current_user)

@router.get("/check-client-sop/{client_id}")
def check_client_sop(
    client_id: str,
    db: Session = Depends(get_db),
    current_user: Any = Depends(get_current_user)
):
    exists = SOPService.check_sop_exists(client_id, db)
    return {"exists": exists}

@router.get("/stats", response_model=SOPStatsResponse)
def get_sop_stats(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    return SOPService.get_sop_stats(db, current_user)

@router.get("", response_model=SOPListResponse)
def get_sops(
    skip: int = 0,
    limit: int = 100,
    search: Optional[str] = None,
    status_code: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    organisation_id: Optional[str] = None,
    created_by: Optional[str] = None,
    client_id: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    sops, total = SOPService.get_sops(
        db,
        current_user=current_user,
        skip=skip,
        limit=limit,
        search=search,
        status_code=status_code,
        from_date=from_date,
        to_date=to_date,
        organisation_id=organisation_id,
        created_by=created_by,
        client_id=client_id
    )
    return {"sops": sops, "total": total}

@router.post("/ai/extract-sop", response_model=AISOPExtractResponse, status_code=200)
async def ai_extract_sop(
    file: UploadFile = File(...),
    current_user = Depends(get_current_user)
):
    allowed_types = {
        "application/pdf",
        "image/png",
        "image/jpeg",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    }

    if file.content_type not in allowed_types:
        raise HTTPException(400, "Unsupported file type")

    temp_file_path = None

    try:
        # ✅ OS-safe temp file
        with tempfile.NamedTemporaryFile(
            delete=False,
            suffix=f"_{uuid.uuid4().hex}"
        ) as tmp:
            temp_file_path = tmp.name
            tmp.write(await file.read())

        # ---- extract raw text ----
        text = await AISOPService.extract_text(
            temp_file_path,
            file.content_type
        )

        if not text.strip():
            raise HTTPException(422, "No readable text found")

        # ---- AI extraction ----
        structured = await AISOPService.ai_extract_sop_structured(text)

        return {
            "source_file": file.filename,
            "extracted_data": structured
        }

    except Exception as e:
        raise HTTPException(500, str(e))

    finally:
        # ✅ guaranteed cleanup
        if temp_file_path and os.path.exists(temp_file_path):
            os.remove(temp_file_path)

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
    current_user: User = Depends(Permission("SOPS", "UPDATE"))
):
    updated_sop = SOPService.update_sop(sop_id, sop.model_dump(exclude_unset=True), db)
    if not updated_sop:
        raise HTTPException(status_code=404, detail="SOP not found")
    return updated_sop

@router.patch("/{sop_id}", response_model=SOPResponse)
def update_sop_status(
    sop_id: str,
    status_update: SOPStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(Permission("SOPS", "UPDATE"))
):
    updated_sop = SOPService.update_sop(sop_id, status_update.model_dump(), db)
    if not updated_sop:
        raise HTTPException(status_code=404, detail="SOP not found")
    return updated_sop

@router.delete("/{sop_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_sop(
    sop_id: str, 
    db: Session = Depends(get_db),
    current_user: User = Depends(Permission("SOPS", "DELETE"))
):
    success = SOPService.delete_sop(sop_id, db)
    if not success:
        raise HTTPException(status_code=404, detail="SOP not found")
    return None

@router.get("/{sop_id}/pdf")
def download_sop_pdf(
    sop_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(Permission("SOPS", "EXPORT"))
):
    sop = SOPService.get_sop_by_id(sop_id, db)
    if not sop:
        raise HTTPException(status_code=404, detail="SOP not found")
    
    pdf_buffer = SOPService.generate_sop_pdf(sop)
    filename = sop.get('title', 'SOP').replace(' ', '_')
    return StreamingResponse(
        io.BytesIO(pdf_buffer),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}.pdf"}
    )
