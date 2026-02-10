from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, WebSocket, WebSocketDisconnect, BackgroundTasks, Query
from sqlalchemy import select
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID
import json

from app.models.organisation import Organisation
from app.models.user_client import UserClient
from ..core.database import get_db
from ..core.security import get_current_user
from ..core.permissions import Permission
from ..services.document_service import DocumentService, document_service
from ..services.websocket_manager import websocket_manager
from ..models.document import Document
from ..models.user import User
from ..models.form import FormField
from ..models.client import Client
from ..models.document_type import DocumentType
from ..services.activity_service import ActivityService
from fastapi import Request
import asyncio
# from app.services.document_service import build_derived_document_counts

router = APIRouter(prefix="/api/documents", tags=["documents"])

document_service= DocumentService()


@router.post("/upload", response_model=List[dict])
async def upload_documents(
    files: List[UploadFile] = File(...),
    enable_ai: bool = Form(True),
    document_type_id: Optional[UUID] = Form(None),
    template_id: Optional[UUID] = Form(None),
    form_id: Optional[UUID] = Form(None),
    form_data: Optional[str] = Form(None),
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db),
    _: bool = Depends(Permission("documents", "CREATE")),
    background_tasks: BackgroundTasks = None,
    request: Request = None,
):
    """
    Upload multiple documents.
    Client ownership is enforced server-side.
    """

    # ─────────────────────────────
    # 1. BASIC VALIDATION
    # ─────────────────────────────
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")

    for file in files:
        if file.size and file.size > 1024 * 1024 * 1024:
            raise HTTPException(
                status_code=400,
                detail=f"File {file.filename} exceeds 1GB limit",
            )

    # ─────────────────────────────
    # 2. PARSE form_data ONCE
    # ─────────────────────────────
    parsed_form_data: dict = {}

    if form_data:
        try:
            parsed_form_data = json.loads(form_data)
            if not isinstance(parsed_form_data, dict):
                raise ValueError
        except Exception:
            raise HTTPException(
                status_code=400,
                detail="Invalid form_data JSON",
            )

    # ─────────────────────────────
    # 3. ENFORCE CLIENT OWNERSHIP
    # ─────────────────────────────
    frontend_client_id = parsed_form_data.get("client_id")

    client_id = current_user.client_id
    client_name = None

    if current_user.is_client and current_user.client_id:
        client = (
            db.query(Client)
            .filter(Client.id == current_user.client_id)
            .first()
        )
        if client:
            client_name = (
                client.business_name
                or f"{client.first_name} {client.last_name}".strip()
            )


        # 🔒 FORCE client_id (ignore frontend completely)
        enforced_client_id = str(current_user.client_id)

    else:
        # Admin / Staff users
        enforced_client_id = frontend_client_id

    if enforced_client_id:
        parsed_form_data["client_id"] = enforced_client_id

    # Serialize back
    final_form_data = json.dumps(parsed_form_data) if parsed_form_data else None

    # ─────────────────────────────
    # 4. PROCESS UPLOAD
    # ─────────────────────────────
    documents = await document_service.process_multiple_uploads(
        db=db,
        files=files,
        user=current_user,
        enable_ai=enable_ai,
        document_type_id=document_type_id,
        template_id=template_id,
        form_id=form_id,
        form_data=final_form_data,
    )

    # ─────────────────────────────
    # 5. ACTIVITY LOG
    # ─────────────────────────────
    for doc in documents:
        ActivityService.log(
            db=db,
            action="CREATE",
            entity_type="document",
            entity_id=str(doc.id),
            user_id=current_user.id,
            details={
                "filename": doc.filename,
                "size": doc.file_size,
            },
            request=request,
            background_tasks=background_tasks,
        )

    # ─────────────────────────────
    # 6. RESPONSE
    # ─────────────────────────────
    return [
        {
            "id": doc.id,
            "filename": doc.filename,
            "status_id": doc.status_id,
            "statusCode": doc.status.code if doc.status else None,
            "file_size": doc.file_size,
            "upload_progress": doc.upload_progress,
        }
        for doc in documents
    ]


@router.get("/{document_id}/form-data")
async def get_document_form_data(
    document_id: int,
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db),
    permission: bool = Depends(Permission("documents", "READ"))
):
    document = (
        DocumentService
        ._document_access_query(db, current_user)
        .filter(Document.id == document_id)
        .first()
    )

    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    if not document.form_data_relation:
        return {"data": {}, "form_id": None}

    # ---- resolve fields ----
    resolved_data = {}

    if document.form_data_relation.data:
        from ..models.form import FormField
        from ..models.client import Client
        from ..models.document_type import DocumentType

        for field_id, value in document.form_data_relation.data.items():
            field = db.query(FormField).filter(FormField.id == field_id).first()

            if not field:
                resolved_data[field_id] = value
                continue

            display_value = value

            if field.field_type == "client_dropdown":
                client = db.query(Client).filter(Client.id == value).first()
                if client:
                    display_value = client.business_name or f"{client.first_name} {client.last_name}".strip()

            elif field.field_type == "document_type_dropdown":
                doc_type = db.query(DocumentType).filter(DocumentType.id == value).first()
                if doc_type:
                    display_value = doc_type.name

            resolved_data[field.label] = display_value

    return {
        "data": resolved_data,
        "form_id": document.form_data_relation.form_id,
        "updated_at": document.form_data_relation.updated_at
    }


@router.patch("/{document_id}/form-data")
async def update_document_form_data(
    document_id: int,
    form_data: dict, 
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    permission: bool = Depends(Permission("documents", "UPDATE")),
    background_tasks: BackgroundTasks = None,
    request: Request = None
):
    """Update form data for a document with role-based access control"""
    from ..models.user_role import UserRole
    from ..models.role import Role
    from ..models.status import Status
    from ..models.user_client import UserClient
    from ..models.client import Client
    from ..models.document_form_data import DocumentFormData
    from sqlalchemy import cast, String, or_
    
    # Get user's roles to determine access level
    user_roles = db.query(Role.name).join(UserRole).join(User).filter(
        User.id == current_user.id,
        Role.status_id.in_(
            db.query(Status.id).filter(Status.code == 'ACTIVE')
        )
    ).all()
    
    role_names = [role.name for role in user_roles]
    is_admin = any(role in ['ADMIN', 'SUPER_ADMIN'] for role in role_names)
    
    query = DocumentService._document_access_query(db, current_user)
    document = query.filter(Document.id == document_id).first()

    
    if not is_admin:
        # assigned_client_ids = db.query(UserClient.client_id).filter(
        #     UserClient.user_id == current_user.id
        # ).subquery()
        assigned_client_ids = select(UserClient.client_id).where(
            UserClient.user_id == current_user.id
        )
        
        client_documents_query = db.query(Document.id).join(
            DocumentFormData, Document.id == DocumentFormData.document_id
        ).join(
            Client, cast(DocumentFormData.data['client_id'], String) == cast(Client.id, String)
        ).filter(
            Client.id.in_(assigned_client_ids)
        )
        
        query = query.filter(
            or_(
                Document.created_by == current_user.id,
                Document.id.in_(client_documents_query)
            )
        )
    
    document = query.first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    
    from ..models.document_form_data import DocumentFormData
    from ..models.form import FormField
    from ..models.client import Client
    from ..models.document_type import DocumentType
    
    # Helper for resolving data with human-readable labels and values
    def resolve_resolved_data(data_dict):
        resolved = {}
        for field_id, value in data_dict.items():
            field = db.query(FormField).filter(FormField.id == field_id).first()
            if field:
                display_value = value
                
                # Check for specific field types or labels for system fields
                is_client = field.field_type == 'client_dropdown' or field.label == 'Client'
                is_doc_type = field.field_type == 'document_type_dropdown' or field.label == 'Document Type'
                
                if field.field_type == 'dropdown' and field.options:
                    for option in field.options:
                        if option.get('value') == value:
                            display_value = option.get('label', value)
                            break
                elif is_client:
                    try:
                        client = db.query(Client).filter(Client.id == value).first()
                        if client:
                            display_value = client.business_name or f"{client.first_name} {client.last_name}".strip()
                    except Exception:
                        pass
                elif is_doc_type:
                    try:
                        doc_type = db.query(DocumentType).filter(DocumentType.id == value).first()
                        if doc_type:
                            display_value = doc_type.name
                    except Exception:
                        pass
                resolved[field.label] = display_value
            else:
                resolved[field_id] = value
        return resolved

    # Capture old and new resolved data to calculate changes
    old_data_raw = document.form_data_relation.data if document.form_data_relation else {}
    resolved_old = resolve_resolved_data(old_data_raw)
    resolved_new = resolve_resolved_data(form_data)
    
    changes = ActivityService.calculate_changes(resolved_old, resolved_new)

    # Update client_id in the Document record if present in form_data
    client_id = DocumentService.extract_client_id_from_form_data(db, form_data)
    if client_id:
        document.client_id = client_id

    if not document.form_data_relation:
        # Create if not exists (though typically created on upload)
        new_record = DocumentFormData(
            document_id=document.id,
            data=form_data
        )
        db.add(new_record)
    else:
        document.form_data_relation.data = form_data
        
    db.commit()

    # Activity Log
    ActivityService.log(
        db,
        action="UPDATE",
        entity_type="document",
        entity_id=str(document_id),
        user_id=current_user.id,
        details={
            "sub_action": "METADATA_UPDATE",
            "filename": document.filename,
            "changes": changes
        },
        request=request,
        background_tasks=background_tasks
    )

    return {"message": "Form data updated"}

@router.get("/stats")
def get_document_stats(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    permission: bool = Depends(Permission("documents", "READ"))
):
    """Get aggregate document statistics for the cards"""
    return document_service.get_document_stats(
        db=db,
        user=current_user
    )


@router.get("", response_model=dict)
def get_documents(
    skip: int = 0,
    limit: int = 25,
    status_id: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    search_query: Optional[str] = None,
    form_filters: Optional[str] = None,
    document_type_id: Optional[UUID] = None,  # ADD
    shared_only: bool = False,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    permission: bool = Depends(Permission("documents", "READ"))
):
    """Get user documents with filters"""
    documents, total_count = document_service.get_user_documents(
        db=db,
        current_user=current_user,
        skip=skip,
        limit=limit,
        status_id=status_id,
        date_from=date_from,
        date_to=date_to,
        search_query=search_query,
        form_filters=form_filters,
        document_type_id=document_type_id,
        shared_only=shared_only
    )

    # Get all form fields for this user's scope (simplified to all for now as it's small)
    fields = db.query(FormField).all()
    field_map = {str(f.id): f for f in fields}
    
    # Get all clients
    # Determine role
    if isinstance(current_user, Organisation):
    # ORG LOGIN → show all org clients
        clients = db.query(Client).filter(
            Client.organisation_id == current_user.id
        ).all()

    elif isinstance(current_user, User):

        role_names = [r.name for r in current_user.roles]
        is_admin = any(r in ["ADMIN", "SUPER_ADMIN"] for r in role_names)

        if is_admin:
            clients = db.query(Client).all()
        else:
            clients = (
                db.query(Client)
                .join(UserClient, UserClient.client_id == Client.id)
                .filter(UserClient.user_id == current_user.id)
                .all()
            )

    else:
        clients = []

    client_map = {str(c.id): c for c in clients}
    
    # Get all document types
    doc_types = db.query(DocumentType).all()
    doc_type_map = {str(dt.id): dt for dt in doc_types}

    # Helper function to resolve form data using pre-fetched maps
    def resolve_form_data(form_data_dict):
        if not form_data_dict:
            return {}
        
        resolved_data = {}
        for field_id, value in form_data_dict.items():
            field = field_map.get(str(field_id))
            if field:
                display_value = value
                if field.field_type == 'client_dropdown':
                    client = client_map.get(str(value))
                    if client:
                        display_value = client.business_name or f"{client.first_name} {client.last_name}".strip()
                elif field.field_type == 'document_type_dropdown':
                    doc_type = doc_type_map.get(str(value))
                    if doc_type:
                        display_value = doc_type.name
                resolved_data[field.label] = display_value
            else:
                resolved_data[field_id] = value
        return resolved_data
    
    result = [
        {
            "id": doc.id,
            "filename": doc.filename,
            "original_filename": doc.original_filename,
            "status_id": doc.status_id,
            "statusCode": doc.status.code if doc.status else None,
            "file_size": doc.file_size,
            "upload_progress": doc.upload_progress,
            "error_message": doc.error_message,
            "total_pages": doc.total_pages,
            "created_at": doc.created_at.isoformat() if doc.created_at else None,
            "updated_at": doc.updated_at.isoformat() if doc.updated_at else None,
            "is_archived": doc.is_archived,
            "custom_form_data": resolve_form_data(doc.form_data_relation.data if doc.form_data_relation else {})
        }
        for doc in documents
    ]

    return {
        "documents": result,
        "total": total_count,
        "page": (skip // limit) + 1 if limit > 0 else 1,
        "page_size": limit
    }

@router.get("/{document_id}")
async def get_document_detail(
    document_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    permission: bool = Depends(Permission("documents", "READ"))
):
    """Get document details including extracted data"""
    document = document_service.get_document_detail(
        db,
        document_id,
        current_user
    )
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    derived_counts = document_service.build_derived_document_counts(document.extracted_documents,document.unverified_documents)

    return {
        "id": document.id,
        "filename": document.filename,
        "original_filename": document.original_filename,
        "status_id": document.status_id,
        "statusCode": document.status.code if document.status else None,
        "file_size": document.file_size,
        "derived_documents": derived_counts,   # 👈 NEW (what UI should use)
        "content_type": document.content_type,
        "total_pages": document.total_pages,
        "upload_progress": document.upload_progress,
        "error_message": document.error_message,
        "created_at": document.created_at.isoformat(),
        "updated_at": document.updated_at.isoformat(),
        "analysis_report_s3_key": document.analysis_report_s3_key,
        "is_archived": document.is_archived,
        "extracted_documents": [
            {
                "id": str(ed.id),
                "document_type": ed.document_type.name.upper() if ed.document_type else None,
                "page_range": ed.page_range,
                "confidence": ed.confidence,
                "extracted_data": ed.extracted_data
            } for ed in document.extracted_documents
        ],
        "unverified_documents": [
            {
                "id": str(ud.id),
                "suspected_type": ud.suspected_type,
                "page_range": ud.page_range,
                "status": ud.status
            } for ud in document.unverified_documents
        ]
    }
@router.get("/{document_id}/preview-url")
async def get_document_preview_url(
    document_id: int,
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db),
    permission: bool = Depends(Permission("documents", "READ"))
):
    document = (
        DocumentService
        ._document_access_query(db, current_user)
        .filter(Document.id == document_id)
        .first()
    )

    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    if not document.s3_key:
        raise HTTPException(status_code=404, detail="File not uploaded")
    
    from ..services.s3_service import s3_service
    presigned_url = s3_service.generate_presigned_url(document.s3_key, expiration=3600)

    if not presigned_url:
        raise HTTPException(status_code=500, detail="Failed to generate preview URL")

    return {"url": presigned_url}

# @router.get("/{document_id}/preview-url")
# async def get_document_preview_url(
#     document_id: int,
#     current_user: User = Depends(get_current_user),
#     db: Session = Depends(get_db),
#     permission: bool = Depends(Permission("documents", "READ"))
# ):
#     """Get secure, temporary pre-signed URL for preview with role-based access control"""
#     from ..models.user_role import UserRole
#     from ..models.role import Role
#     from ..models.status import Status
#     from ..models.user_client import UserClient
#     from ..models.client import Client
#     from ..models.document_form_data import DocumentFormData
#     from sqlalchemy import cast, String, or_
    
#     # Get user's roles to determine access level
#     user_roles = db.query(Role.name).join(UserRole).join(User).filter(
#         User.id == current_user.id,
#         Role.status_id.in_(
#             db.query(Status.id).filter(Status.code == 'ACTIVE')
#         )
#     ).all()
    
#     role_names = [role.name for role in user_roles]
#     is_admin = any(role in ['ADMIN', 'SUPER_ADMIN'] for role in role_names)
    
#     query = DocumentService._document_access_query(db, current_user)
#     document = query.filter(Document.id == document_id).first()

    
#     if not is_admin:
#         # assigned_client_ids = db.query(UserClient.client_id).filter(
#         #     UserClient.user_id == current_user.id
#         # ).subquery()
#         assigned_client_ids = select(UserClient.client_id).where(
#             UserClient.user_id == current_user.id
#         )
#         client_documents_query = db.query(Document.id).join(
#             DocumentFormData, Document.id == DocumentFormData.document_id
#         ).join(
#             Client, cast(DocumentFormData.data['client_id'], String) == cast(Client.id, String)
#         ).filter(
#             Client.id.in_(assigned_client_ids)
#         )
        
#         query = query.filter(
#             or_(
#                 Document.created_by == current_user.id,
#                 Document.id.in_(client_documents_query)
#             )
#         )
    
#     document = query.first()
#     if not document or not document.s3_key:
#         raise HTTPException(status_code=404, detail="Document not found")
        
#     from ..services.s3_service import s3_service
    
#     presigned_url = s3_service.generate_presigned_url(document.s3_key, expiration=3600)
#     if not presigned_url:
#         raise HTTPException(status_code=500, detail="Failed to generate preview URL")
        
#     return {"url": presigned_url}
@router.get("/{document_id}/download-url")
async def get_document_download_url(
    document_id: int,
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db),
    permission: bool = Depends(Permission("documents", "EXPORT")),
    background_tasks: BackgroundTasks = None,
    request: Request = None
):
    """
    Secure download URL.
    Uses centralized access control only.
    """

    document = (
        DocumentService
        ._document_access_query(db, current_user)
        .filter(Document.id == document_id)
        .first()
    )

    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    if not document.s3_key:
        raise HTTPException(status_code=404, detail="File not uploaded")

    from ..services.s3_service import s3_service

    filename = document.original_filename or document.filename
    disposition = f'attachment; filename="{filename}"'

    presigned_url = s3_service.generate_presigned_url(
        document.s3_key,
        expiration=3600,
        response_content_disposition=disposition
    )

    if not presigned_url:
        raise HTTPException(status_code=500, detail="Failed to generate download URL")

    ActivityService.log(
        db,
        action="DOWNLOAD",
        entity_type="document",
        entity_id=str(document_id),
        user_id=str(current_user.id),
        details={"filename": filename},
        request=request,
        background_tasks=background_tasks
    )

    return {"url": presigned_url}


@router.get("/{document_id}/report-url")
async def get_document_report_url(
    document_id: int,
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db),
    permission: bool = Depends(Permission("documents", "EXPORT")),
    background_tasks: BackgroundTasks = None,
    request: Request = None
):
    """Download analysis report"""

    document = (
        DocumentService
        ._document_access_query(db, current_user)
        .filter(Document.id == document_id)
        .first()
    )

    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    if not document.analysis_report_s3_key:
        raise HTTPException(status_code=404, detail="Analysis report not found")

    from ..services.s3_service import s3_service

    filename = f"analysis_report_{document.filename}.xlsx"
    disposition = f'attachment; filename="{filename}"'

    presigned_url = s3_service.generate_presigned_url(
        document.analysis_report_s3_key,
        expiration=3600,
        response_content_disposition=disposition
    )

    if not presigned_url:
        raise HTTPException(status_code=500, detail="Failed to generate report URL")

    ActivityService.log(
        db,
        action="DOWNLOAD_REPORT",
        entity_type="document",
        entity_id=str(document_id),
        user_id=str(current_user.id),
        details={"filename": filename},
        request=request,
        background_tasks=background_tasks
    )

    return {"url": presigned_url}


@router.get("/{document_id}/report-data")
async def get_document_report_data(
    document_id: int,
    page: int = Query(None),
    current_user = Depends(get_current_user),
    db: Session = Depends(get_db),
    permission: bool = Depends(Permission("documents", "READ"))
):
    document = (
        DocumentService
        ._document_access_query(db, current_user)
        .filter(Document.id == document_id)
        .first()
    )

    if not document or not document.analysis_report_s3_key:
        raise HTTPException(status_code=404, detail="Analysis report not found")

    from ..services.s3_service import s3_service
    import pandas as pd, io, json

    file_bytes = await s3_service.download_file(document.analysis_report_s3_key)
    df = pd.read_excel(io.BytesIO(file_bytes))

    findings = []

    for _, row in df.iterrows():
        page_range = row.get("Page Range", "")

        if page is not None:
            if not page_range:
                continue

            match = False
            for part in str(page_range).split(","):
                part = part.strip()
                if "-" in part:
                    start, end = map(int, part.split("-"))
                    if start <= page <= end:
                        match = True
                else:
                    if int(part) == page:
                        match = True

            if not match:
                continue

        raw = row.get("Extracted Data", "{}")

        try:
            if isinstance(raw, dict):
                extracted = raw
            else:
                extracted = json.loads(str(raw).replace("'", '"'))
        except:
            extracted = {"raw": str(raw)}

        findings.append({
            "document_type": row.get("Document Type", "Unknown"),
            "page_range": str(page_range),
            "extracted_data": extracted
        })

    return {
        "findings": findings,
        "total_pages": document.total_pages
    }

@router.post("/{document_id}/cancel")
async def cancel_document(
    document_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    permission: bool = Depends(Permission("documents", "UPDATE")),
    background_tasks: BackgroundTasks = None,
    request: Request = None
):
    """Cancel document analysis"""
    success = await document_service.cancel_document_analysis(
        db,
        document_id,
        current_user
    )

    if not success:
        raise HTTPException(status_code=404, detail="Document not found")
    
    # Activity Log
    ActivityService.log(
        db,
        action="UPDATE",
        entity_type="document",
        entity_id=str(document_id),
        user_id=current_user.id,
        details={"sub_action": "CANCEL_ANALYSIS"},
        request=request,
        background_tasks=background_tasks
    )

    return {"message": "Analysis cancelled"}

@router.post("/{document_id}/reanalyze")
async def reanalyze_document(
    document_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    permission: bool = Depends(Permission("documents", "UPDATE")),
    background_tasks: BackgroundTasks = None,
    request: Request = None
):
    """Re-analyze document"""
    try:
        await document_service.reanalyze_document(
            db,
            document_id,
            current_user
        )


        
        # Activity Log
        ActivityService.log(
            db,
            action="UPDATE",
            entity_type="document",
            entity_id=str(document_id),
            user_id=current_user.id,
            details={"sub_action": "REANALYZE"},
            request=request,
            background_tasks=background_tasks
        )
        
        return {"message": "Document queued for re-analysis"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/{document_id}/archive")
async def archive_document(
    document_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    permission: bool = Depends(Permission("documents", "UPDATE")),
    background_tasks: BackgroundTasks = None,
    request: Request = None
):
    """Archive a document"""
    success = await document_service.archive_document(
        db,
        document_id,
        current_user
    )


    if not success:
        raise HTTPException(status_code=404, detail="Document not found")
    
    ActivityService.log(
        db,
        action="UPDATE",
        entity_type="document",
        entity_id=str(document_id),
        user_id=current_user.id,
        details={"sub_action": "ARCHIVE"},
        request=request,
        background_tasks=background_tasks
    )
    return {"message": "Document archived successfully"}

@router.post("/{document_id}/unarchive")
async def unarchive_document(
    document_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    permission: bool = Depends(Permission("documents", "UPDATE")),
    background_tasks: BackgroundTasks = None,
    request: Request = None
):
    """Unarchive a document"""
    success = await document_service.unarchive_document(
        db,
        document_id,
        current_user
    )


    if not success:
        raise HTTPException(status_code=404, detail="Document not found")
        
    ActivityService.log(
        db,
        action="UPDATE",
        entity_type="document",
        entity_id=str(document_id),
        user_id=current_user.id,
        details={"sub_action": "UNARCHIVE"},
        request=request,
        background_tasks=background_tasks
    )
    return {"message": "Document unarchived successfully"}

@router.delete("/{document_id}")
async def delete_document(
    document_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    permission: bool = Depends(Permission("documents", "DELETE")),
    background_tasks: BackgroundTasks = None,
    request: Request = None
):
    """Delete a document"""
    filename = await document_service.delete_document(
        db,
        document_id,
        current_user
    )

    if not filename:
        raise HTTPException(status_code=404, detail="Document not found")
    
    ActivityService.log(
        db,
        action="DELETE",
        entity_type="document",
        entity_id=str(document_id),
        user_id=current_user.id,
        details={"filename": filename},
        request=request,
        background_tasks=background_tasks
    )
    return {"message": "Document deleted successfully"}

@router.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str = "ae5b4fa6-44bb-45ce-beac-320bb4e21697"):
    """WebSocket endpoint for real-time document status updates"""
    await websocket_manager.connect(websocket, user_id)
    try:
        while True:
            # Keep connection alive
            await websocket.receive_text()
    except WebSocketDisconnect:
        websocket_manager.disconnect(websocket, user_id)