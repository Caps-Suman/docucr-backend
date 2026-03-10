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
from app.models.sop import SOP, SOPDocument
from app.models.sop_provider_mapping import SopProviderMapping
from app.models.status import Status
from app.services.activity_service import ActivityService
from fastapi import Request, BackgroundTasks
from sqlalchemy import or_, desc

from app.core.database import get_db
from app.models.user import User
from app.models.client import Client
from app.services.ai_sop_service import AISOPService
from app.services.sop_service import SOPService
from app.services.s3_service import s3_service
from app.core.security import get_current_user
from app.core.permissions import Permission

router = APIRouter()
class BillingRule(BaseModel):
    description: str
    source: Optional[str] = None

class BillingGuidelineGroup(BaseModel):
    category: str
    rules: list[BillingRule]


class PayerGuideline(BaseModel):
    payerName: str
    description: str
    payerId: Optional[str] = None
    eraStatus: Optional[str] = None
    ediStatus: Optional[str] = None
    tfl: Optional[str] = None
    networkStatus: Optional[str] = None
    mailingAddress: Optional[str] = None
    source: Optional[str] = None
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

class SOPDocumentResponse(BaseModel):
    id: UUID
    name: str
    category: str
    s3_key: str
    created_at: Any
    document_url: Optional[str] = None
    processed: Optional[bool] = False
    billing_guidelines: Optional[List[Dict[str, Any]]] = None
    payer_guidelines: Optional[List[Dict[str, Any]]] = None
    coding_rules_cpt: Optional[List[Dict[str, Any]]] = None
    coding_rules_icd: Optional[List[Dict[str, Any]]] = None

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
    documents: List[SOPDocumentResponse] = []
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
    documents: List[SOPDocumentResponse] = []
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

@router.post("/{sop_id}/documents/process", status_code=202)
async def process_extra_documents(
    sop_id: UUID,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(Permission("SOPs", "UPDATE"))
):
    """
    Triggers background extraction for all unprocessed extra documents
    belonging to this SOP. Returns immediately (202 Accepted).
    The client should poll GET /{sop_id} to check document.processed status.
    """
    sop = db.query(SOP).filter(SOP.id == sop_id).first()
    if not sop:
        raise HTTPException(404, "SOP not found")

    unprocessed = db.query(SOPDocument).filter(
        SOPDocument.sop_id == sop_id,
        SOPDocument.category != "Source file",
        SOPDocument.processed == False
    ).all()

    if not unprocessed:
        return {"message": "No unprocessed documents found", "queued": 0}

    # Run extraction for each doc independently in background
    # so one failure doesn't block others
    for doc in unprocessed:
        background_tasks.add_task(
            _extract_single_document,
            doc_id=str(doc.id),
            sop_id=str(sop_id),
        )

    return {
        "message": f"Extraction queued for {len(unprocessed)} document(s)",
        "queued": len(unprocessed),
        "document_ids": [str(doc.id) for doc in unprocessed]
    }


def _extract_single_document(doc_id: str, sop_id: str):
    """
    Background task: extract a single extra document and apply to SOP.
    Runs in a separate thread via FastAPI BackgroundTasks.
    """
    from app.core.database import SessionLocal

    db = SessionLocal()
    try:
        doc = db.query(SOPDocument).filter(SOPDocument.id == doc_id).first()
        db_sop = db.query(SOP).filter(SOP.id == sop_id).first()

        if not doc or not db_sop:
            print(f"[extraction] Doc {doc_id} or SOP {sop_id} not found")
            return

        # Download from S3 and extract text + structure
        extracted = SOPService.extract_from_document(doc)

        # Filter extracted data to only the relevant section for this doc's category
        category = doc.category or ""

        # Mapping to SOPDocument fields (category-based filtering)
        if "Payer" in category:
            doc.payer_guidelines = extracted.get("payer_guidelines", [])
        elif "Billing" in category:
            doc.billing_guidelines = extracted.get("billing_guidelines", [])
        elif "Coding" in category or "CPT" in category or "ICD" in category:
            doc.coding_rules_cpt = extracted.get("coding_rules_cpt", [])
            doc.coding_rules_icd = extracted.get("coding_rules_icd", [])
        elif "Workflow" in category or "Eligibility" in category:
            # Note: SOPDocument doesn't have workflow_process fields yet, 
            # but we still apply it to the main SOP below.
            pass

        # Merge extracted data into the SOP fields
        # (This updates the main SOP table fields while keeping sources separate)
        SOPService.apply_extraction_to_sop(
            sop=db_sop,
            doc=doc,
            category=category,
            extracted=extracted,
        )

        doc.processed = True
        db.commit()
        print(f"[extraction] Doc {doc_id} processed successfully")

    except Exception as e:
        print(f"[extraction] Doc {doc_id} failed: {e}")
        # Don't mark as processed so it can be retried

    finally:
        db.close()

@router.post("/check-client-sop")
def check_client_sop(
    client_id: UUID = Body(...),
    provider_ids: List[UUID] = Body(default=[]),
    db: Session = Depends(get_db),
    permission: bool = Depends(Permission("SOPs", "CREATE")),
    current_user: User = Depends(get_current_user)
):
    org_id = current_user.organisation_id

    active_status_id = db.query(Status.id).filter(
        Status.code == "ACTIVE",
        Status.type == "GENERAL"
    ).scalar()

    extracting_status_id = db.query(Status.id).filter(
        Status.code == "EXTRACTING",
        Status.type == "GENERAL"
    ).scalar()

    allowed_statuses = [s for s in [active_status_id, extracting_status_id] if s]

    client_sops = (
        db.query(SOP.id)
        .filter(
            SOP.client_id == client_id,
            SOP.organisation_id == org_id,
            SOP.status_id.in_(allowed_statuses),
        )
        .all()
    )
    client_sop_ids = [row[0] for row in client_sops]

    if not provider_ids:
        if not client_sop_ids:
            return {"exists": False, "blocked_provider_ids": []}

        sop_ids_with_providers = (
            db.query(SopProviderMapping.sop_id)
            .filter(SopProviderMapping.sop_id.in_(client_sop_ids))
            .distinct()
            .all()
        )
        sop_ids_with_providers = {row[0] for row in sop_ids_with_providers}

        client_level_sop_exists = any(
            sid not in sop_ids_with_providers for sid in client_sop_ids
        )

        return {
            "exists": client_level_sop_exists,
            "blocked_provider_ids": [],
        }

    if not client_sop_ids:
        return {"exists": False, "blocked_provider_ids": []}

    blocked = (
        db.query(SopProviderMapping.provider_id)
        .filter(
            SopProviderMapping.sop_id.in_(client_sop_ids),
            SopProviderMapping.provider_id.in_(provider_ids),
        )
        .all()
    )

    blocked_ids = [str(row[0]) for row in blocked]

    return {
        "exists": len(blocked_ids) > 0,
        "blocked_provider_ids": blocked_ids,
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
        # guaranteed cleanup
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
    current_user: User = Depends(get_current_user)
):
    allowed_types = {
        "application/pdf",
        "image/png",
        "image/jpeg",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.ms-excel",
    }

    if file.content_type not in allowed_types:
        raise HTTPException(400, "Unsupported file type")

    file_content = await file.read()

    # Resolve org_id (super admin inherits from client)
    org_id = current_user.organisation_id
    if not org_id:
        client = db.query(Client).filter(Client.id == client_id).first()
        org_id = client.organisation_id if client else None

    active_status = db.query(Status.id).filter(
        Status.code == "ACTIVE",
        Status.type == "GENERAL"
    ).scalar()

    extracting_status = db.query(Status.id).filter(
        Status.code == "EXTRACTING",
        Status.type == "GENERAL"
    ).scalar()

    allowed_statuses = [s for s in [active_status, extracting_status] if s]

    # All active/extracting SOPs for this client in this org
    client_sop_ids = [
        row[0] for row in db.query(SOP.id).filter(
            SOP.client_id == client_id,
            SOP.organisation_id == org_id,
            SOP.status_id.in_(allowed_statuses),
        ).all()
    ]

    if not provider_ids:
        # Creating a client-level SOP (no providers).
        # Only block if there is already a client-level SOP (a SOP with no provider mappings).
        if client_sop_ids:
            sop_ids_with_providers = {
                row[0] for row in db.query(SopProviderMapping.sop_id)
                .filter(SopProviderMapping.sop_id.in_(client_sop_ids))
                .distinct()
                .all()
            }
            client_level_exists = any(
                sid not in sop_ids_with_providers for sid in client_sop_ids
            )
            if client_level_exists:
                raise HTTPException(
                    status_code=400,
                    detail="This client already has a client-level SOP."
                )
    else:
        # Creating a provider-linked SOP.
        # Only block if one of the selected providers is already mapped to an active SOP for this client.
        if client_sop_ids:
            existing_provider = (
                db.query(SopProviderMapping)
                .filter(
                    SopProviderMapping.sop_id.in_(client_sop_ids),
                    SopProviderMapping.provider_id.in_(provider_ids),
                )
                .first()
            )
            if existing_provider:
                raise HTTPException(
                    status_code=400,
                    detail="One or more providers already have an active SOP for this client."
                )

    new_sop = SOP(
        title=file.filename,
        provider_type=provider_type,
        category="Uncategorized",
        client_id=client_id,
        coding_rules_cpt=[],
        coding_rules_icd=[],
        status_id=extracting_status,
        created_by=current_user.id,
        organisation_id=org_id,
    )
    db.add(new_sop)
    db.commit()
    db.refresh(new_sop)

    # Save file to S3 permanently
    try:
        s3_key = f"sops/{new_sop.id}/{file.filename}"
        await s3_service.upload_file(
            io.BytesIO(file_content),
            file.filename,
            file.content_type,
            s3_key=s3_key
        )

        db.add(SOPDocument(
            sop_id=new_sop.id,
            name=file.filename,
            category="Source file",
            s3_key=s3_key
        ))
        db.commit()
    except Exception as e:
        failed_status = db.query(Status).filter(
            Status.code == "FAILED", Status.type == "DOCUMENT"
        ).first()
        new_sop.status_id = failed_status.id if failed_status else new_sop.status_id
        db.commit()
        raise HTTPException(500, f"Failed to upload to S3: {str(e)}")

    if provider_ids:
        for pid in provider_ids:
            db.add(SopProviderMapping(
                sop_id=new_sop.id,
                provider_id=pid,
                created_by=str(current_user.id)
            ))
        db.commit()

    file_ext = os.path.splitext(file.filename)[1]
    with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as tmp:
        temp_file_path = tmp.name
        tmp.write(file_content)

    background_tasks.add_task(
        AISOPService.process_sop_extraction,
        new_sop.id,
        temp_file_path,
        file.content_type
    )

    return {"sop_id": str(new_sop.id)}

@router.post("/sops/{sop_id}/reanalyse", status_code=202)
async def reanalyse_sop(
    sop_id: UUID,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    sop = db.query(SOP).filter(SOP.id == sop_id).first()
    if not sop:
        raise HTTPException(404, "SOP not found")
    
    # Find the "Source file" document
    source_doc = next((doc for doc in sop.documents if doc.category == "Source file"), None)
    
    if not source_doc:
        raise HTTPException(400, "SOP source file not found. Please re-upload.")

    # Get EXTRACTING status
    extracting_status = db.query(Status).filter(
        Status.code == "EXTRACTING",
        Status.type == "GENERAL"
    ).first()

    if not extracting_status:
        raise HTTPException(500, "EXTRACTING status not configured")

    # Update status to extracting
    sop.status_id = extracting_status.id
    db.commit()

    # Determine content type from filename (simplified)
    s3_key = source_doc.s3_key
    content_type = "application/pdf" # default
    if s3_key.endswith(".docx"):
        content_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    elif s3_key.endswith(".xlsx"):
        content_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    elif s3_key.endswith((".png", ".jpg", ".jpeg")):
        content_type = "image/png" if s3_key.endswith(".png") else "image/jpeg"

    # Background task will need to handle downloading from S3
    background_tasks.add_task(
        AISOPService.process_sop_extraction,
        sop.id,
        None, # No local file path yet
        content_type,
        s3_key=s3_key
    )

    return {"message": "Reanalysis started", "sop_id": str(sop.id)}

@router.post("/sops/{sop_id}/stop", status_code=200)
async def stop_sop(
    sop_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    sop = db.query(SOP).filter(SOP.id == sop_id).first()
    if not sop:
        raise HTTPException(404, "SOP not found")
    
    failed_status = db.query(Status).filter(
        Status.code == "FAILED",
        Status.type == "DOCUMENT"
    ).first()

    if not failed_status:
        raise HTTPException(500, "FAILED status not configured")

    sop.status_id = failed_status.id
    db.commit()

    return {"message": "Extraction stopped", "sop_id": str(sop.id)}

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

    new_sop.billing_guidelines = []
    new_sop.payer_guidelines = []
    new_sop.coding_rules_cpt = []
    new_sop.coding_rules_icd = []

    # Create a document record to hold the extracted data
    source_name = "AI Extracted Data"
    def inject_source(items):
        if not items: return items
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict):
                    if "rules" in item:
                        for r in item["rules"]:
                            r["source"] = source_name
                    else:
                        item["source"] = source_name
        return items

    source_doc = SOPDocument(
        sop_id=new_sop.id,
        name=source_name,
        category="Source file",
        s3_key="",  # No physical file in this specific flow
        processed=True,
        billing_guidelines=inject_source(extracted_data.get("billing_guidelines", [])),
        payer_guidelines=inject_source(extracted_data.get("payer_guidelines", [])),
        coding_rules_cpt=inject_source(extracted_data.get("coding_rules_cpt", [])),
        coding_rules_icd=inject_source(extracted_data.get("coding_rules_icd", []))
    )
    db.add(source_doc)

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
@router.post("/{sop_id}/documents", response_model=SOPDocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_sop_document(
    sop_id: UUID,
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    category: str = Form("Source file"),
    extracted_data: str = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(Permission("SOPs", "UPDATE"))
):
    sop = db.query(SOP).filter(SOP.id == sop_id).first()
    if not sop:
        raise HTTPException(404, "SOP not found")

    file_content = await file.read()
    s3_key = f"sops/{sop.id}/{file.filename}"
    
    try:
        # If this is a "Source file", delete existing ones first (ensure only 1 source file)
        if category == "Source file":
            old_docs = db.query(SOPDocument).filter(
                SOPDocument.sop_id == sop.id,
                SOPDocument.category == "Source file"
            ).all()
            for old_doc in old_docs:
                try:
                    await s3_service.delete_file(old_doc.s3_key)
                except:
                    pass
                db.delete(old_doc)
            db.flush()

        await s3_service.upload_file(
            io.BytesIO(file_content),
            file.filename,
            file.content_type,
            s3_key=s3_key
        )
        
        new_doc = SOPDocument(
            sop_id=sop.id,
            name=file.filename,
            category=category,
            s3_key=s3_key
        )
        
        if extracted_data:
            import json
            try:
                parsed_data = json.loads(extracted_data)
                
                def inject_source(items, source_name):
                    if not items: return []
                    for item in items:
                        if isinstance(item, dict):
                            item['source'] = source_name
                            if 'rules' in item and isinstance(item['rules'], list):
                                for rule in item['rules']:
                                    if isinstance(rule, dict):
                                        rule['source'] = source_name
                    return items
                
                doc_source_name = "source_file" if category == "Source file" else file.filename
                new_doc.billing_guidelines = inject_source(parsed_data.get('billing_guidelines', []), doc_source_name)
                new_doc.payer_guidelines = inject_source(parsed_data.get('payer_guidelines', []), doc_source_name)
                new_doc.coding_rules_cpt = inject_source(parsed_data.get('coding_rules_cpt', []), doc_source_name)
                new_doc.coding_rules_icd = inject_source(parsed_data.get('coding_rules_icd', []), doc_source_name)
                
                new_doc.status = "COMPLETED"
                new_doc.processed = True
            except json.JSONDecodeError:
                raise HTTPException(400, "Invalid JSON in extracted_data")
        
        db.add(new_doc)
        db.commit()
        db.refresh(new_doc)
        
        ActivityService.log(
            db=db,
            action="upload",
            entity_type="SOP Document",
            entity_id=str(new_doc.id),
            current_user=current_user,
            details={
                "sop_id": str(sop.id),
                "filename": file.filename,
                "category": category,
                "sop_title": sop.title
            },
            request=request
        )
        
        # Return formatted response to ensure proper serialization
        return {
            "id": str(new_doc.id),
            "name": new_doc.name,
            "category": new_doc.category,
            "s3_key": new_doc.s3_key,
            "created_at": new_doc.created_at,
            "processed": new_doc.processed,
            "billing_guidelines": new_doc.billing_guidelines,
            "payer_guidelines": new_doc.payer_guidelines,
            "coding_rules_cpt": new_doc.coding_rules_cpt,
            "coding_rules_icd": new_doc.coding_rules_icd
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(500, f"Failed to upload document: {str(e)}")

@router.delete("/{sop_id}/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_sop_document(
    sop_id: UUID,
    document_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(Permission("SOPs", "UPDATE"))
):
    doc = db.query(SOPDocument).filter(
        SOPDocument.id == document_id,
        SOPDocument.sop_id == sop_id
    ).first()
    
    if not doc:
        raise HTTPException(404, "Document not found")
    
    try:
        # Delete from S3
        await s3_service.delete_file(doc.s3_key)
        
        # Delete from database
        db.delete(doc)
        db.commit()

        ActivityService.log(
            db=db,
            action="delete",
            entity_type="SOP Document",
            entity_id=str(document_id),
            current_user=current_user,
            details={
                "sop_id": str(sop_id),
                "filename": doc.name,
                "category": doc.category
            },
            request=request
        )
        db.commit()
        
        return None
    except Exception as e:
        db.rollback()
        raise HTTPException(500, f"Failed to delete document: {str(e)}")

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

@router.get("/{sop_id}/source-file")
async def download_sop_source_file(
    sop_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    sop = SOPService.get_sop_by_id(sop_id, db, current_user)
    if not sop:
        raise HTTPException(404, "SOP not found")
    
    # Find the "Source file" document
    source_doc = next((doc for doc in sop.get("documents", []) if doc.get("category") == "Source file"), None)
    
    if not source_doc:
        raise HTTPException(404, "Source file not found for this SOP")
    
    s3_key = source_doc.get("s3_key")
    try:
        file_content = await s3_service.download_file(s3_key)
        filename = source_doc.get("name") or os.path.basename(s3_key)
        
        # Determine media type based on extension
        media_type = "application/octet-stream"
        if filename.endswith(".pdf"):
            media_type = "application/pdf"
        elif filename.endswith(".docx"):
            media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        elif filename.endswith((".png", ".jpg", ".jpeg")):
            media_type = f"image/{filename.split('.')[-1]}"
            
        return StreamingResponse(
            io.BytesIO(file_content),
            media_type=media_type,
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    except Exception as e:
        raise HTTPException(500, f"Failed to download source file: {str(e)}")