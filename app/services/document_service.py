from sqlalchemy.orm import Session
from ..models.document import Document
from ..services.s3_service import s3_service
from ..services.websocket_manager import websocket_manager
from fastapi import UploadFile
import asyncio
from typing import List

class DocumentService:
    
    @staticmethod
    async def create_document(db: Session, file: UploadFile, user_id: str) -> Document:
        """Create document record in database"""
        document = Document(
            filename=file.filename,
            original_filename=file.filename,
            file_size=file.size,
            content_type=file.content_type,
            user_id=user_id,
            status_id="QUEUED"
        )
        db.add(document)
        db.commit()
        db.refresh(document)
        return document
    
    @staticmethod
    async def update_document_status(db: Session, document_id: int, status_id: str, 
                                   progress: int = 0, error_message: str = None, 
                                   s3_key: str = None, s3_bucket: str = None):
        """Update document status and notify via WebSocket"""
        document = db.query(Document).filter(Document.id == document_id).first()
        if document:
            document.status_id = status_id
            document.upload_progress = progress
            if error_message:
                document.error_message = error_message
            if s3_key:
                document.s3_key = s3_key
            if s3_bucket:
                document.s3_bucket = s3_bucket
            
            db.commit()
            
            # Send WebSocket notification
            await websocket_manager.broadcast_document_status(
                document_id=document.id,
                status=status_id,
                user_id=str(document.user_id),
                progress=progress,
                error_message=error_message
            )
    
    @staticmethod
    async def upload_document_to_s3(db: Session, document_id: int, file: UploadFile):
        """Upload document to S3 with status updates"""
        try:
            # Update status to UPLOADING
            await DocumentService.update_document_status(
                db, document_id, "UPLOADING", progress=0
            )
            
            # Upload to S3
            s3_key, bucket_name = await s3_service.upload_file(
                file.file, file.filename, file.content_type
            )
            
            # Update status to UPLOADED
            await DocumentService.update_document_status(
                db, document_id, "UPLOADED", 
                progress=100, s3_key=s3_key, s3_bucket=bucket_name
            )
            
        except Exception as e:
            # Update status with error
            await DocumentService.update_document_status(
                db, document_id, "FAILED", 
                error_message=str(e)
            )
            raise e
    
    @staticmethod
    async def process_multiple_uploads(db: Session, files: List[UploadFile], user_id: str):
        """Create document records immediately and return, process uploads in background"""
        documents = []
        file_buffers = []
        from io import BytesIO
        
        # Create all document records first with QUEUED status
        for file in files:
            # We must buffer the file content because FastAPI closes UploadFile 
            # as soon as the request handler returns.
            content = await file.read()
            file_size = len(content)
            buffer = BytesIO(content)
            
            # Reset original file just in case (though we use buffer now)
            await file.seek(0)
            
            document = Document(
                filename=file.filename,
                original_filename=file.filename,
                file_size=file_size,
                content_type=file.content_type,
                user_id=user_id,
                status_id="QUEUED",
                upload_progress=0
            )
            db.add(document)
            db.flush()  # Get the ID without committing
            documents.append(document)
            
            # Store buffer and metadata for background task
            # We can't pass UploadFile to background task as it will be closed
            file_buffers.append({
                'buffer': buffer,
                'filename': file.filename,
                'content_type': file.content_type
            })
        
        db.commit()  # Commit all documents at once
        
        # Immediately notify about queued documents
        for document in documents:
            await websocket_manager.broadcast_document_status(
                document_id=document.id,
                status="QUEUED",
                user_id=str(document.user_id),
                progress=0
            )
        
        # Start background upload processing (don't await)
        # We pass the buffers instead of the UploadFile objects
        asyncio.create_task(DocumentService._process_uploads_background(db, documents, file_buffers))
        
        return documents
    
    @staticmethod
    async def _process_single_upload(document_id: int, file_data: dict):
        """Process a single document upload"""
        # Create a new database session for this task
        from ..core.database import SessionLocal
        db = SessionLocal()
        
        try:
            # Update status to UPLOADING
            await DocumentService.update_document_status(
                db, document_id, "UPLOADING", progress=10
            )
            
            # Fetch document to get user_id for WS notifications
            document = db.query(Document).filter(Document.id == document_id).first()
            if not document:
                raise Exception("Document not found")
                
            # Upload to S3 with progress updates
            # Define progress callback
            total_size = len(file_data['buffer'].getvalue())
            uploaded_bytes = 0
            main_loop = asyncio.get_event_loop()
            
            def progress_callback(bytes_amount):
                nonlocal uploaded_bytes
                uploaded_bytes += bytes_amount
                # Map 0-100% to 10-99% range so we don't hit 100 before final confirmation
                percentage = min(int((uploaded_bytes / total_size) * 90) + 10, 99) 
                
                # Send WS update via threadsafe call to main loop
                # Check if we have user_id (we should)
                if document and document.user_id:
                     asyncio.run_coroutine_threadsafe(
                        websocket_manager.broadcast_document_status(
                            document_id=document_id,
                            status="UPLOADING",
                            user_id=str(document.user_id),
                            progress=percentage
                        ),
                        main_loop
                    )

            s3_key, bucket_name = await s3_service.upload_file(
                file_data['buffer'], 
                file_data['filename'], 
                file_data['content_type'],
                progress_callback=progress_callback
            )
            
            # Update status to UPLOADED
            await DocumentService.update_document_status(
                db, document_id, "UPLOADED", 
                progress=100, s3_key=s3_key, s3_bucket=bucket_name
            )
            
        except Exception as e:
            # Update status with error
            await DocumentService.update_document_status(
                db, document_id, "FAILED", 
                error_message=str(e)
            )
            print(f"Failed to upload document {document_id}: {str(e)}")
        finally:
            db.close()

    @staticmethod
    async def _process_uploads_background(db: Session, documents: List[Document], files_data: List[dict]):
        """Process uploads in background in parallel"""
        try:
            # Process all uploads in parallel
            await asyncio.gather(
                *[DocumentService._process_single_upload(doc.id, file_data) 
                  for doc, file_data in zip(documents, files_data)]
            )
        except Exception as e:
            print(f"Error in background processing: {e}")
    
    @staticmethod
    def get_user_documents(db: Session, user_id: str, skip: int = 0, limit: int = 100) -> List[Document]:
        """Get documents for a user"""
        return db.query(Document).filter(Document.user_id == user_id).offset(skip).limit(limit).all()
    
    @staticmethod
    async def delete_document(db: Session, document_id: int, user_id: str) -> bool:
        """Delete a document and its S3 file"""
        document = db.query(Document).filter(
            Document.id == document_id, 
            Document.user_id == user_id
        ).first()
        
        if not document:
            return False
        
        # Delete from S3 if exists
        if document.s3_key:
            await s3_service.delete_file(document.s3_key)
        
        # Delete from database
        db.delete(document)
        db.commit()
        return True

document_service = DocumentService()