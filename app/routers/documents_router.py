from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID
from ..core.database import get_db
from ..core.security import get_current_user
from ..services.document_service import document_service
from ..services.websocket_manager import websocket_manager
from ..models.document import Document
from ..models.user import User
import asyncio

router = APIRouter(prefix="/api/documents", tags=["documents"])

@router.post("/upload", response_model=List[dict])
async def upload_documents(
    files: List[UploadFile] = File(...),
    enable_ai: bool = Form(False),
    document_type_id: Optional[UUID] = Form(None),
    template_id: Optional[UUID] = Form(None),
    form_id: Optional[UUID] = Form(None),
    form_data: Optional[str] = Form(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Upload multiple documents - returns immediately with queued status"""
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")
    
    # Validate file sizes (max 1GB per file)
    for file in files:
        if file.size and file.size > 1024 * 1024 * 1024:  # 1GB
            raise HTTPException(status_code=400, detail=f"File {file.filename} exceeds 1GB limit")
    
    # Create document records immediately and start background processing
    documents = await document_service.process_multiple_uploads(
        db, files, current_user.id, enable_ai, document_type_id, template_id, form_id, form_data
    )
    
    return [
        {
            "id": doc.id,
            "filename": doc.filename,
            "status_id": doc.status_id,
            "statusCode": doc.status.code if doc.status else None,
            "file_size": doc.file_size,
            "upload_progress": doc.upload_progress
        }
        for doc in documents
    ]

# ... existing get_documents ...

@router.get("/{document_id}/form-data")
async def get_document_form_data(
    document_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get form data for a document"""
    document = db.query(Document).filter(
        Document.id == document_id, 
        Document.user_id == current_user.id
    ).first()
    
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
        
    if not document.form_data_relation:
         return {"data": {}, "form_id": None}
    
    # Resolve field IDs to field names
    resolved_data = {}
    if document.form_data_relation.data:
        from ..models.form import FormField
        from ..models.client import Client
        from ..models.document_type import DocumentType
        
        for field_id, value in document.form_data_relation.data.items():
            field = db.query(FormField).filter(FormField.id == field_id).first()
            if field:
                # Resolve dropdown values if needed
                display_value = value
                if field.field_type == 'dropdown' and field.options:
                    # Find the option label for the value
                    for option in field.options:
                        if option.get('value') == value:
                            display_value = option.get('label', value)
                            break
                elif field.field_type == 'client_dropdown':
                    # Resolve client ID to client name
                    try:
                        client = db.query(Client).filter(Client.id == value).first()
                        if client:
                            display_value = client.business_name or f"{client.first_name} {client.last_name}".strip()
                    except:
                        pass
                elif field.field_type == 'document_type_dropdown':
                    # Resolve document type ID to document type name
                    try:
                        doc_type = db.query(DocumentType).filter(DocumentType.id == value).first()
                        if doc_type:
                            display_value = doc_type.name
                    except:
                        pass
                        
                resolved_data[field.label] = display_value
            else:
                # Field not found, keep original
                resolved_data[field_id] = value
         
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
    db: Session = Depends(get_db)
):
    """Update form data for a document"""
    document = db.query(Document).filter(
        Document.id == document_id, 
        Document.user_id == current_user.id
    ).first()
    
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    
    from ..models.document_form_data import DocumentFormData
    
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
    return {"message": "Form data updated"}

@router.get("/stats")
async def get_document_stats(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get aggregate document statistics for the cards"""
    return document_service.get_document_stats(db, current_user.id)

@router.get("/", response_model=List[dict])
async def get_documents(
    skip: int = 0,
    limit: int = 100,
    status_id: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    search_query: Optional[str] = None,
    form_filters: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get user documents with filters"""
    documents = document_service.get_user_documents(
        db, current_user.id, skip, limit,
        status_id, date_from, date_to, search_query, form_filters
    )
    
    # Helper function to resolve form data
    def resolve_form_data(form_data_dict):
        if not form_data_dict:
            return {}
        
        from ..models.form import FormField
        from ..models.client import Client
        from ..models.document_type import DocumentType
        
        resolved_data = {}
        for field_id, value in form_data_dict.items():
            field = db.query(FormField).filter(FormField.id == field_id).first()
            if field:
                display_value = value
                if field.field_type == 'client_dropdown':
                    try:
                        client = db.query(Client).filter(Client.id == value).first()
                        if client:
                            display_value = client.business_name or f"{client.first_name} {client.last_name}".strip()
                    except:
                        pass
                elif field.field_type == 'document_type_dropdown':
                    try:
                        doc_type = db.query(DocumentType).filter(DocumentType.id == value).first()
                        if doc_type:
                            display_value = doc_type.name
                    except:
                        pass
                resolved_data[field.label] = display_value
            else:
                resolved_data[field_id] = value
        return resolved_data
    
    return [
        {
            "id": doc.id,
            "filename": doc.filename,
            "original_filename": doc.original_filename,
            "status_id": doc.status_id,
            "statusCode": doc.status.code if doc.status else None,
            "file_size": doc.file_size,
            "upload_progress": doc.upload_progress,
            "error_message": doc.error_message,
            "created_at": doc.created_at.isoformat(),
            "updated_at": doc.updated_at.isoformat(),
            "is_archived": doc.is_archived,
            "custom_form_data": resolve_form_data(doc.form_data_relation.data if doc.form_data_relation else {})
        }
        for doc in documents
    ]

@router.get("/{document_id}")
async def get_document_detail(
    document_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get document details including extracted data"""
    document = document_service.get_document_detail(db, document_id, current_user.id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    
    return {
        "id": document.id,
        "filename": document.filename,
        "original_filename": document.original_filename,
        "status_id": document.status_id,
        "statusCode": document.status.code if document.status else None,
        "file_size": document.file_size,
        "content_type": document.content_type,
        "upload_progress": document.upload_progress,
        "error_message": document.error_message,
        "created_at": document.created_at.isoformat(),
        "updated_at": document.updated_at.isoformat(),
        "analysis_report_s3_key": document.analysis_report_s3_key,
        "is_archived": document.is_archived,
        "extracted_documents": [
            {
                "id": str(ed.id),
                "document_type": ed.document_type.name if ed.document_type else None,
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
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get secure, temporary pre-signed URL for preview (enables streaming/seeking)"""
    document = db.query(Document).filter(
        Document.id == document_id,
        Document.user_id == current_user.id
    ).first()
    
    if not document or not document.s3_key:
        raise HTTPException(status_code=404, detail="Document not found")
        
    from ..services.s3_service import s3_service
    
    presigned_url = s3_service.generate_presigned_url(document.s3_key, expiration=3600)
    if not presigned_url:
        raise HTTPException(status_code=500, detail="Failed to generate preview URL")
        
    return {"url": presigned_url}

@router.get("/{document_id}/download-url")
async def get_document_download_url(
    document_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get secure download URL"""
    document = db.query(Document).filter(
        Document.id == document_id,
        Document.user_id == current_user.id
    ).first()
    
    if not document or not document.s3_key:
        raise HTTPException(status_code=404, detail="Document not found")
        
    from ..services.s3_service import s3_service
    
    # Force download with correct filename
    filename = document.original_filename or document.filename
    disposition = f'attachment; filename="{filename}"'
    
    presigned_url = s3_service.generate_presigned_url(
        document.s3_key, 
        expiration=3600,
        response_content_disposition=disposition
    )
    
    if not presigned_url:
        raise HTTPException(status_code=500, detail="Failed to generate download URL")
        
    return {"url": presigned_url}

@router.get("/{document_id}/report-url")
async def get_document_report_url(
    document_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get secure download URL for the analysis report"""
    document = db.query(Document).filter(
        Document.id == document_id,
        Document.user_id == current_user.id
    ).first()
    
    if not document or not document.analysis_report_s3_key:
        raise HTTPException(status_code=404, detail="Analysis report not found")
        
    from ..services.s3_service import s3_service
    
    # Force download with generic name or derived from doc name
    filename = f"analysis_report_{document.filename}.xlsx"
    disposition = f'attachment; filename="{filename}"'
    
    presigned_url = s3_service.generate_presigned_url(
        document.analysis_report_s3_key, 
        expiration=3600,
        response_content_disposition=disposition
    )
    
    if not presigned_url:
        raise HTTPException(status_code=500, detail="Failed to generate report URL")
        
    return {"url": presigned_url}

@router.post("/{document_id}/cancel")
async def cancel_document(
    document_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Cancel document analysis"""
    success = await document_service.cancel_document_analysis(db, document_id, current_user.id)
    if not success:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"message": "Analysis cancelled"}

@router.post("/{document_id}/reanalyze")
async def reanalyze_document(
    document_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Re-analyze document"""
    try:
        await document_service.reanalyze_document(db, document_id, current_user.id)
        return {"message": "Document queued for re-analysis"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/{document_id}/archive")
async def archive_document(
    document_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Archive a document"""
    success = await document_service.archive_document(db, document_id, current_user.id)
    if not success:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"message": "Document archived successfully"}

@router.post("/{document_id}/unarchive")
async def unarchive_document(
    document_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Unarchive a document"""
    success = await document_service.unarchive_document(db, document_id, current_user.id)
    if not success:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"message": "Document unarchived successfully"}

@router.delete("/{document_id}")
async def delete_document(
    document_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a document"""
    success = await document_service.delete_document(db, document_id, current_user.id)
    if not success:
        raise HTTPException(status_code=404, detail="Document not found")
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