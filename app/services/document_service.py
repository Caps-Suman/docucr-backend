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
                db, document_id, "UPLOAD_FAILED", 
                error_message=str(e)
            )
            raise e
    
    @staticmethod
    async def process_multiple_uploads(db: Session, files: List[UploadFile], user_id: str, 
                                     enable_ai: bool = False, document_type_id: str = None, 
                                     template_id: str = None, form_id: str = None, form_data: str = None):
        """Create document records immediately and return, process uploads in background"""
        documents = []
        file_buffers = []
        from io import BytesIO
        import json
        from ..models.document_form_data import DocumentFormData
        
        parsed_form_data = None
        if form_data:
            try:
                parsed_form_data = json.loads(form_data)
            except:
                parsed_form_data = {}
        
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
                upload_progress=0,
                enable_ai=enable_ai,
                document_type_id=document_type_id,
                template_id=template_id
            )
            db.add(document)
            db.flush()  # Get the ID without committing
            documents.append(document)
            
            # Create Form Data Record if exists
            if parsed_form_data or form_id:
                form_data_record = DocumentFormData(
                    document_id=document.id,
                    form_id=form_id,
                    data=parsed_form_data
                )
                db.add(form_data_record)

            
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
        asyncio.create_task(DocumentService._process_uploads_background(
            documents, file_buffers, enable_ai, document_type_id, template_id
        ))
        
        return documents
    
    @staticmethod
    async def _process_uploads_background(documents: List[Document], files_data: List[dict],
                                        enable_ai: bool = False, document_type_id: str = None, 
                                        template_id: str = None):
        """Process uploads in background: Upload All -> Then Process AI Sequentially"""
        try:
            # Step 1: Upload all documents in parallel
            # We use a modified single upload that only handles S3 upload
            upload_tasks = []
            for doc, file_data in zip(documents, files_data):
                upload_tasks.append(
                    DocumentService._process_single_upload_only(doc.id, file_data)
                )
            
            # Wait for all uploads to complete
            results = await asyncio.gather(*upload_tasks, return_exceptions=True)
            
            # Identify successfully uploaded documents
            successful_docs = []
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    print(f"Upload failed for document {documents[i].id}: {result}")
                else:
                    successful_docs.append((documents[i], files_data[i]))
            
            # Step 2: If AI enabled, process sequentially
            if enable_ai and successful_docs:
                from ..core.database import SessionLocal
                db = SessionLocal()
                try:
                    for doc, file_data in successful_docs:
                        # Update status to Queued for AI
                        await DocumentService.update_document_status(
                            db, doc.id, "AI_QUEUED", 
                            progress=0, error_message="Queued for AI Analysis"
                        )
                finally:
                    db.close()
                
                # Process one by one
                # Note: _process_single_ai_analysis creates its own session, which is fine.
                for doc, file_data in successful_docs:
                    await DocumentService._process_single_ai_analysis(
                        doc.id, file_data, document_type_id, template_id
                    )

        except Exception as e:
            print(f"Error in background processing: {e}")

    @staticmethod
    async def _process_single_upload_only(document_id: int, file_data: dict):
        """Handle ONLY the S3 upload part"""
        # Create new session
        from ..core.database import SessionLocal
        db = SessionLocal()
        
        try:
            # Update status to UPLOADING
            await DocumentService.update_document_status(
                db, document_id, "UPLOADING", progress=10
            )
            
            # Fetch document
            document = db.query(Document).filter(Document.id == document_id).first()
            if not document:
                raise Exception("Document not found")
                
            file_bytes = file_data['buffer'].getvalue()
            total_size = len(file_bytes)
            uploaded_bytes = 0
            main_loop = asyncio.get_event_loop()
            
            # Reset buffer
            file_data['buffer'].seek(0)
            
            def progress_callback(bytes_amount):
                nonlocal uploaded_bytes
                uploaded_bytes += bytes_amount
                percentage = min(int((uploaded_bytes / total_size) * 90) + 10, 99) 
                
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

            # Generate structured S3 key: user_id/document_id_filename
            # Sanitize filename (basic)
            safe_filename = "".join([c for c in file_data['filename'] if c.isalnum() or c in ('._-')]).strip()
            # If empty after sanitization, fallback to doc_id
            if not safe_filename:
                safe_filename = f"doc_{document_id}"
                
            custom_s3_key = f"documents/{document.user_id}/{document_id}_{safe_filename}"

            # Create a separate buffer for S3 upload to protect the original one
            from io import BytesIO
            s3_buffer = BytesIO(file_bytes)

            s3_key, bucket_name = await s3_service.upload_file(
                s3_buffer, 
                file_data['filename'], 
                file_data['content_type'],
                progress_callback=progress_callback,
                s3_key=custom_s3_key
            )

            # Update status to UPLOADED
            await DocumentService.update_document_status(
                db, document_id, "UPLOADED", 
                progress=100, s3_key=s3_key, s3_bucket=bucket_name
            )
            
            return True

        except Exception as e:
            await DocumentService.update_document_status(
                db, document_id, "UPLOAD_FAILED", 
                error_message=str(e)
            )
            raise e
        finally:
            db.close()

    @staticmethod
    async def _process_single_ai_analysis(document_id: int, file_data: dict, 
                                        document_type_id: str = None, template_id: str = None):
        """Handle ONLY the AI analysis part"""
        from ..core.database import SessionLocal
        db = SessionLocal()
        
        try:
            # Update status to ANALYZING
            await DocumentService.update_document_status(
                db, document_id, "ANALYZING", 
                progress=0, error_message="Starting Analysis..."
            )
            
            document = db.query(Document).filter(Document.id == document_id).first()
            if not document:
                raise Exception("Document not found")

            # Setup Progress Callback
            # main_loop capture not strictly needed if we just await inside this async func
            async def report_ai_progress(msg, pct):
                # We update the DB so that page refreshes show the latest status message
                await DocumentService.update_document_status(
                    db, document_id, "ANALYZING", 
                    progress=pct, error_message=msg
                )

            # Capture bytes
            file_bytes = file_data['buffer'].getvalue()

            # ... [Prepare DB models imports] ...
            from ..models.template import Template
            from ..models.document_type import DocumentType
            from ..models.extracted_document import ExtractedDocument
            from ..models.unverified_document import UnverifiedDocument
            from ..services.ai_service import ai_service
            
            # Build schemas
            schemas = []
            templates = db.query(Template).all()
            template_map = {str(t.document_type_id): t for t in templates}
            doc_types = db.query(DocumentType).all()
            doc_type_map = {t.name: t for t in doc_types}
            
            for dt in doc_types:
                t = template_map.get(str(dt.id))
                if t:
                    schemas.append({
                        "type_name": dt.name,
                        "fields": t.extraction_fields
                    })

            # Define Cancellation Check Callback
            async def check_cancelled():
                # We need a fresh check
                check_db = SessionLocal()
                try:
                    current_doc = check_db.query(Document).filter(Document.id == document_id).first()
                    return current_doc and current_doc.status_id == 'CANCELLED'
                finally:
                    check_db.close()

            # Call AI Service
            analysis_result = await ai_service.analyze_document(
                file_bytes, 
                file_data['filename'], 
                schemas,
                progress_callback=report_ai_progress,
                check_cancelled_callback=check_cancelled
            )
            
            # Process Findings
            findings = analysis_result.get("findings", [])
            excel_rows = []

            for finding in findings:
                f_type = finding.get("type", "Unknown")
                f_range = finding.get("page_range")
                f_data = finding.get("data")
                f_confidence = finding.get("confidence", 0.0)
                
                excel_rows.append({
                    "Document Type": f_type,
                    "Page Range": f_range,
                    "Extracted Data": str(f_data)
                })

                doc_type_obj = doc_type_map.get(f_type)
                if doc_type_obj:
                    t = template_map.get(str(doc_type_obj.id))
                    extracted_doc = ExtractedDocument(
                        document_id=document.id,
                        document_type_id=doc_type_obj.id,
                        template_id=t.id if t else None,
                        extracted_data=f_data,
                        page_range=f_range,
                        confidence=f_confidence
                    )
                    db.add(extracted_doc)
                else:
                    unverified_doc = UnverifiedDocument(
                        document_id=document.id,
                        suspected_type=f_type,
                        page_range=f_range,
                        extracted_data=f_data,
                        status="PENDING"
                    )
                    db.add(unverified_doc)
            
            db.commit()

            # Excel Report
            if excel_rows:
                import pandas as pd
                import io
                df = pd.DataFrame(excel_rows)
                excel_buffer = io.BytesIO()
                with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                    df.to_excel(writer, index=False, sheet_name='Analysis Report')
                excel_buffer.seek(0)
                
                report_s3_key, _ = await s3_service.upload_file(
                    excel_buffer, 
                    f"analysis_report_{document_id}.xlsx", 
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
                document.analysis_report_s3_key = report_s3_key
                db.commit()

            # Final Status
            await DocumentService.update_document_status(
                db, document_id, "COMPLETED", 
                progress=100, error_message="Analysis Complete"
            )

        except Exception as e:
            error_str = str(e)
            is_cancelled = "Analysis Cancelled" in error_str
            
            await DocumentService.update_document_status(
                db, document_id, "CANCELLED" if is_cancelled else "AI_FAILED", 
                error_message="Analysis Cancelled" if is_cancelled else error_str
            )
            print(f"AI Analysis {'Cancelled' if is_cancelled else 'Failed'} for {document_id}: {e}")
        finally:
            db.close()
    
    @staticmethod
    def get_user_documents(db: Session, user_id: str, skip: int = 0, limit: int = 100,
                         status_id: str = None, date_from: str = None, date_to: str = None,
                         search_query: str = None, form_filters: str = None) -> List[Document]:
        """Get documents for a user with filters"""
        from sqlalchemy.orm import joinedload
        from sqlalchemy import and_, or_, cast, String, text
        from ..models.document_form_data import DocumentFormData
        import json
        from datetime import datetime

        query = db.query(Document)\
            .options(joinedload(Document.form_data_relation))\
            .filter(Document.user_id == user_id)

        # Status Filter
        if status_id:
            query = query.filter(Document.status_id == status_id)

        # Date Filters
        if date_from:
            try:
                # Expecting ISO format string or YYYY-MM-DD
                d_from = datetime.fromisoformat(date_from.replace("Z", "+00:00"))
                query = query.filter(Document.created_at >= d_from)
            except ValueError:
                pass # Ignore invalid dates

        if date_to:
            try:
                d_to = datetime.fromisoformat(date_to.replace("Z", "+00:00"))
                query = query.filter(Document.created_at <= d_to)
            except ValueError:
                pass

        # Search Query (General - filename)
        if search_query:
            query = query.filter(Document.filename.ilike(f"%{search_query}%"))

        # Dynamic Form Filters
        if form_filters:
            try:
                filters = json.loads(form_filters)
                if filters:
                    # Join if not already implicit (joinedload is for loading, but we need to filter)
                    # We outerjoin to include docs even if they don't have form data? 
                    # No, if we are filtering BY form data, they must have it.
                    query = query.join(Document.form_data_relation)
                    
                    for key, value in filters.items():
                        if value:
                            # Use JSON path filtering. 
                            # Cast to string for ILIKE comparison to support partial/case-insensitive match
                            query = query.filter(
                                cast(DocumentFormData.data[key], String).ilike(f"%{value}%")
                            )
            except json.JSONDecodeError:
                pass

        return query.order_by(Document.created_at.desc())\
            .offset(skip)\
            .limit(limit)\
            .all()

    @staticmethod
    def get_document_detail(db: Session, document_id: int, user_id: str) -> Document:
        """Get document with all details (extracted/unverified docs)"""
        from sqlalchemy.orm import joinedload
        return db.query(Document).options(
            joinedload(Document.extracted_documents),
            joinedload(Document.unverified_documents)
        ).filter(
            Document.id == document_id, 
            Document.user_id == user_id
        ).first()
    
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
            
        # Delete analysis report from S3 if exists
        if document.analysis_report_s3_key:
            await s3_service.delete_file(document.analysis_report_s3_key)
        
        # Delete from database
        db.delete(document)
        db.commit()
        return True

    @staticmethod
    async def cancel_document_analysis(db: Session, document_id: int, user_id: str):
        """Cancel ongoing analysis by setting status"""
        document = db.query(Document).filter(
            Document.id == document_id, 
            Document.user_id == user_id
        ).first()
        
        if not document:
             return False
             
        await DocumentService.update_document_status(
            db, document_id, "CANCELLED",
            error_message="Analysis Cancelled by User"
        )
        return True

    @staticmethod
    async def reanalyze_document(db: Session, document_id: int, user_id: str):
        """Reset status to AI_QUEUED and trigger background analysis"""
        document = db.query(Document).filter(
            Document.id == document_id,
            Document.user_id == user_id
        ).first()
        
        if not document:
            raise Exception("Document not found")
            
        # We need the S3 file to be present
        if not document.s3_key:
             raise Exception("Cannot re-analyze: Original file not found on S3")

        # Reset status immediately to give instant feedback
        await DocumentService.update_document_status(
             db, document_id, "AI_QUEUED", 
             progress=0, error_message="Queued for Re-analysis"
        )

        # Spawn background task for the heavy lifting (S3 download + AI)
        asyncio.create_task(DocumentService._perform_reanalysis_background(document_id, user_id))
        
        return True

    @staticmethod
    async def _perform_reanalysis_background(document_id: int, user_id: str):
        """Background task for re-analysis: Download from S3 -> Start AI"""
        from ..core.database import SessionLocal
        import io
        
        db = SessionLocal()
        try:
            document = db.query(Document).filter(
                Document.id == document_id,
                Document.user_id == user_id
            ).first()
            
            if not document or not document.s3_key:
                return

            # Download from S3 asynchronously
            try:
                file_bytes = await s3_service.download_file(document.s3_key)
                file_content = io.BytesIO(file_bytes)
            except Exception as e:
                await DocumentService.update_document_status(
                    db, document_id, "AI_FAILED", 
                    error_message=f"Failed to retrieve file: {str(e)}"
                )
                return

            file_data = {
                'buffer': file_content,
                'filename': document.filename,
                'content_type': document.content_type
            }
            
            # Start AI Analysis
            # Use stored preferences if available
            doc_type_id = str(document.document_type_id) if document.document_type_id else None
            template_id = str(document.template_id) if document.template_id else None
            
            await DocumentService._process_single_ai_analysis(
                document_id, file_data, doc_type_id, template_id
            )
            
        except Exception as e:
            print(f"Background re-analysis failed: {e}")
        finally:
            db.close()

document_service = DocumentService()