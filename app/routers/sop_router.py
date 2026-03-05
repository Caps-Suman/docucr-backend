import os
import tempfile
import uuid
from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import List, Optional, Any, Dict
from pydantic import BaseModel
from uuid import UUID
import io
from app.models.sop import SOP
from app.models.sop_provider_mapping import SopProviderMapping
from app.models.status import Status
from app.services.activity_service import ActivityService
from fastapi import Request, BackgroundTasks

from app.core.database import get_db
from app.models.user import User
from app.services.ai_sop_service import AISOPService
from app.services.sop_service import SOPService
from app.core.security import get_current_user
from app.core.permissions import Permission

router = APIRouter()
class BillingRule(BaseModel):
    description: str

class BillingGuidelineGroup(BaseModel):
    category: str
    rules: list[BillingRule]


class PayerGuideline(BaseModel):
    payerName:str
    description:str
class SOPBase(BaseModel):
    title: str
    category: str
    provider_type: str
    client_id: Optional[UUID] = None
    provider_info: Optional[Dict[str, Any]] = None
    workflow_process: Optional[Dict[str, Any]] = None
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
    organisation_id: Optional[str] = None
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
    permission: bool = Depends(Permission("SOPs", "CREATE")),
    current_user = Depends(get_current_user),
    request: Request = None,
    background_tasks: BackgroundTasks = None,
):
    sop_data = sop.model_dump()

    client_id = str(sop.client_id) if sop.client_id else None

    if not client_id:
        raise HTTPException(400, "Client ID is required")

    result = SOPService.create_sop(
        sop_data,
        db,
        current_user,
        client_id
    )

    ActivityService.log(
        db=db,
        action="CREATE",
        entity_type="sop",
        entity_id=str(result.id),
        details={"title": result.title},
        current_user=current_user,
        request=request,
        background_tasks=background_tasks
    )

    return result
    # return SOPService.create_sop(sop_data, db, current_user)
@router.post("/check-providers/{client_id}")
def check_providers(
    client_id: str,
    payload: dict,
    db: Session = Depends(get_db),
    permission: bool = Depends(Permission("SOPs", "CREATE")),
    current_user = Depends(get_current_user)
):
    provider_ids = payload.get("provider_ids", [])
    sop_id = payload.get("sop_id")   # 👈 MUST exist

    blocked = SOPService.get_blocked_providers(
        client_id=client_id,
        provider_ids=provider_ids,
        db=db,
        exclude_sop_id=sop_id        # 👈 MUST pass
    )

    return {"blocked_provider_ids": blocked}

from uuid import UUID

@router.post("/check-client-sop")
def check_client_sop(
    client_id: UUID = Body(...),
    provider_ids: List[UUID] = Body(...),
    db: Session = Depends(get_db),
    permission: bool = Depends(Permission("SOPs", "CREATE")),
    current_user :User =Depends(get_current_user)
):
    if not provider_ids:
        return {"exists": False, "blocked_provider_ids": []}

    active_status_id = db.query(Status.id).filter(
        Status.code == "ACTIVE",
        Status.type == "GENERAL"
    ).scalar()

    blocked = (
        db.query(SopProviderMapping.provider_id)
        .join(SOP, SopProviderMapping.sop_id == SOP.id)
        .filter(
            SOP.client_id == client_id,
            SOP.status_id == active_status_id,
            SOP.organisation_id == current_user.organisation_id,
            SopProviderMapping.provider_id.in_(provider_ids)
        )
        .all()
    )

    blocked_ids = [str(p[0]) for p in blocked]

    return {
        "exists": len(blocked_ids) > 0,
        "blocked_provider_ids": blocked_ids
    }
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
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",  # .xlsx
        "application/vnd.ms-excel",  # .xls
    }

    if file.content_type not in allowed_types:
        raise HTTPException(400, "Unsupported file type")

    temp_file_path = None

    try:
        # ✅ OS-safe temp file
        file_ext = os.path.splitext(file.filename)[1]

        with tempfile.NamedTemporaryFile(
            delete=False,
            suffix=file_ext
        ) as tmp:
            temp_file_path = tmp.name
            tmp.write(await file.read())

        # ---- extract raw text ----
        text = await AISOPService.extract_text(
            temp_file_path,
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

@router.post("/background/ai/extract-sop", status_code=202)
async def ai_extract_sop_background(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    provider_type: str = Form(...),
    client_id: UUID = Form(...),
    provider_ids: List[UUID] = Form(None),
    db: Session = Depends(get_db),
    current_user :User= Depends(get_current_user)
):
    allowed_types = {
        "application/pdf",
        "image/png",
        "image/jpeg",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",  # .xlsx
        "application/vnd.ms-excel",  # .xls
    }

    if file.content_type not in allowed_types:
        raise HTTPException(400, "Unsupported file type")

    # Get EXTRACTING status
    extracting_status = db.query(Status).filter(
        Status.code == "EXTRACTING",
        Status.type == "GENERAL"
    ).first()

    if not extracting_status:
        raise HTTPException(500, "EXTRACTING status not configured")

    # Create empty SOP row immediately
    new_sop = SOP(
        title=file.filename,
        provider_type=provider_type,   # ✅ FIX
        category="Uncategorized",       # ✅ FIX - default category
        client_id=client_id,           # ✅ FIX
        coding_rules_cpt=[],
        coding_rules_icd=[],
        status_id=extracting_status.id,
        created_by=current_user.id,
        organisation_id=current_user.organisation_id,
    )
    db.add(new_sop)
    db.commit()
    db.refresh(new_sop)
    # 🔥 LINK PROVIDERS HERE
    if provider_ids:
        for pid in provider_ids:
            db.add(SopProviderMapping(
                sop_id=new_sop.id,
                provider_id=pid,
                created_by=str(current_user.id)
            ))

        db.commit()
    # Save file temporarily
    file_ext = os.path.splitext(file.filename)[1]

    with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as tmp:
        temp_file_path = tmp.name
        tmp.write(await file.read())
    # Run background processing
    background_tasks.add_task(
        AISOPService.process_sop_extraction,
        new_sop.id,
        temp_file_path,
        file.content_type
    )

    return {"sop_id": str(new_sop.id)}

@router.post("/ai/extract-sop-foreground", status_code=200)
async def ai_extract_sop_foreground(
    file: UploadFile = File(...)
):
    file_ext = os.path.splitext(file.filename)[1]

    with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as tmp:
        temp_file_path = tmp.name
        content = await file.read()
        tmp.write(content)

    try:
        text = await AISOPService.extract_text(
            temp_file_path,
        )

        structured = await AISOPService.ai_extract_sop_structured(text)

        return {
            "extracted_data": structured
        }

    finally:
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)

@router.post("/background/ai/from-extracted", status_code=202)
def create_sop_from_extracted(
    extracted_data: dict = Body(...),
    provider_type: str = Body(...),
    client_id: UUID = Body(...),
    provider_ids: List[UUID] = Body(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    extracting_status = db.query(Status).filter(
        Status.code == "EXTRACTING",
        Status.type == "GENERAL"
    ).first()

    new_sop = SOP(
        title="Processing...",
        provider_type=provider_type,
        category="Uncategorized",
        client_id=client_id,
        status_id=extracting_status.id,
        created_by=current_user.id,
        organisation_id=current_user.organisation_id,
    )

    db.add(new_sop)
    db.commit()
    db.refresh(new_sop)

    # Link providers
    if provider_ids:
        for pid in provider_ids:
            db.add(SopProviderMapping(
                sop_id=new_sop.id,
                provider_id=pid,
                created_by=str(current_user.id)
            ))
        db.commit()

    # ---- Apply extracted data ----
    basic = extracted_data.get("basic_information", {})
    workflow = extracted_data.get("workflow_process", {})

    new_sop.title = basic.get("sop_title", "Untitled SOP")
    new_sop.category = basic.get("category", "Uncategorized")

    new_sop.workflow_process = {
        "description": workflow.get("description"),
        "posting_charges_rules": workflow.get("posting_charges_rules"),
        "eligibility_verification_portals": workflow.get(
            "eligibility_verification_portals", []
        )
    }

    new_sop.billing_guidelines = extracted_data.get("billing_guidelines", [])
    new_sop.payer_guidelines = extracted_data.get("payer_guidelines", [])
    new_sop.coding_rules_cpt = extracted_data.get("coding_rules_cpt", [])
    new_sop.coding_rules_icd = extracted_data.get("coding_rules_icd", [])

    # Set ACTIVE
    active_status = db.query(Status).filter(
        Status.code == "ACTIVE",
        Status.type == "GENERAL"
    ).first()

    if active_status:
        new_sop.status_id = active_status.id

    db.commit()
    db.refresh(new_sop)

    return {"sop_id": str(new_sop.id)}
@router.get("/{sop_id}", response_model=SOPResponse)
def get_sop(
    sop_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    sop = SOPService.get_sop_by_id(sop_id, db, current_user)

    if not sop:
        raise HTTPException(404, "SOP not found")

    return sop
@router.put("/{sop_id}", response_model=SOPResponse)
def update_sop(
    sop_id: str, 
    sop: SOPUpdate, 
    db: Session = Depends(get_db),
    current_user: User = Depends(Permission("SOPs", "UPDATE")),
    request: Request = None,
    background_tasks: BackgroundTasks = None,
):
    existing = SOPService.get_sop_by_id(sop_id, db, current_user)

    updated = SOPService.update_sop(
        sop_id,
        sop.model_dump(exclude_unset=True),
        db,
        current_user
    )
    if not updated:
        raise HTTPException(404, "SOP not found")

    changes = ActivityService.calculate_changes(
        existing,
        sop.model_dump(exclude_unset=True)
    )

    ActivityService.log(
        db=db,
        action="UPDATE",
        entity_type="sop",
        entity_id=str(sop_id),
        current_user=current_user,
        details={"title": updated["title"], "changes": changes},
        request=request,
        background_tasks=background_tasks
    )

    return updated


@router.patch("/{sop_id}", response_model=SOPResponse)
def update_sop_status(
    sop_id: str,
    status_update: SOPStatusUpdate,
    db: Session = Depends(get_db),
    request:Request=None,
    background_tasks:BackgroundTasks=None,
    current_user: User = Depends(Permission("SOPs", "UPDATE"))
):
    updated_sop = SOPService.update_sop(
        sop_id,
        status_update.model_dump(),
        db,
        current_user
    )
    if not updated_sop:
        raise HTTPException(status_code=404, detail="SOP not found")
    ActivityService.log(
        db=db,
        action="STATUS_CHANGE",
        entity_type="sop",
        entity_id=str(sop_id),
        current_user=current_user,
        details={"status_id": status_update.status_id},
        request=request,
        background_tasks=background_tasks
    )

    return updated_sop

@router.delete("/{sop_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_sop(
    sop_id: str, 
    db: Session = Depends(get_db),
    request:Request=None,
    background_tasks:BackgroundTasks=None,
    current_user: User = Depends(Permission("SOPs", "DELETE"))
):
    success = SOPService.delete_sop(sop_id, db, current_user)  
    if not success:
        raise HTTPException(status_code=404, detail="SOP not found")
    ActivityService.log(
        db=db,
        action="DELETE",
        entity_type="sop",
        entity_id=str(sop_id),
        current_user=current_user,
        request=request,
        background_tasks=background_tasks
    )

    return None
@router.get("/{sop_id}/pdf")
def download_sop_pdf(
    sop_id: str,
    db: Session = Depends(get_db),
    request: Request = None,
    background_tasks: BackgroundTasks = None,
    current_user: User = Depends(Permission("SOPs", "EXPORT"))
):
    sop = SOPService.get_sop_by_id(sop_id, db, current_user)

    if not sop:
        raise HTTPException(404, "SOP not found")

    pdf_buffer = SOPService.generate_sop_pdf(sop)
    filename = sop.get("title", "SOP").replace(" ", "_")

    ActivityService.log(
        db=db,
        action="EXPORT",
        entity_type="sop",
        entity_id=str(sop_id),
        current_user=current_user,
        details={"title": sop.get("title")},
        request=request,
        background_tasks=background_tasks
    )

    return StreamingResponse(
        io.BytesIO(pdf_buffer),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}.pdf"}
    )