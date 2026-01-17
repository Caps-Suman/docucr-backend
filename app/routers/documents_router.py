from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session
from typing import List
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
    documents = await document_service.process_multiple_uploads(db, files, current_user.id)
    
    return [
        {
            "id": doc.id,
            "filename": doc.filename,
            "status": doc.status_id,
            "file_size": doc.file_size,
            "upload_progress": doc.upload_progress
        }
        for doc in documents
    ]

@router.get("/", response_model=List[dict])
async def get_documents(
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get user documents"""
    documents = document_service.get_user_documents(db, current_user.id, skip, limit)
    return [
        {
            "id": doc.id,
            "filename": doc.filename,
            "original_filename": doc.original_filename,
            "status": doc.status_id,
            "file_size": doc.file_size,
            "upload_progress": doc.upload_progress,
            "error_message": doc.error_message,
            "created_at": doc.created_at.isoformat(),
            "updated_at": doc.updated_at.isoformat()
        }
        for doc in documents
    ]

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