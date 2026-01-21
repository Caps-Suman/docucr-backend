from fastapi import UploadFile
from datetime import datetime
from typing import List, Optional, Dict, Any, Union
import asyncio
import json
from io import BytesIO
from collections import Counter, defaultdict

from sqlalchemy import and_, or_, cast, String, text, func
from sqlalchemy.orm import Session, joinedload

from ..models.document import Document
from ..models.status import Status
from ..models.user import User
from ..models.user_role import UserRole
from ..models.role import Role
from ..models.user_client import UserClient
from ..models.client import Client
from ..models.document_form_data import DocumentFormData
from ..services.s3_service import s3_service
from ..services.websocket_manager import websocket_manager
from ..services.webhook_service import webhook_service
from ..core.database import SessionLocal

class DocumentService:
    @staticmethod
    def get_status_id_by_code(db: Session, code: str) -> int:
        status = db.query(Status).filter(Status.code == code).first()
        if status:
            return status.id
        return None

    @staticmethod
    # def build_derived_document_counts(extracted_docs) -> Dict[str, int]:
    #     counter = Counter()
    #     for ed in extracted_docs:
    #         if ed.document_type:
    #             counter[ed.document_type.name] += 1
    #     return dict(counter)
    
    @staticmethod
    def build_derived_document_counts(extracted_docs, unverified_docs):
        """
        Count LOGICAL documents, not pages.
        """

    # Collect ranges per document type
        ranges_by_type = defaultdict(list)

        # Verified
        for ed in extracted_docs:
            if ed.document_type:
                ranges_by_type[ed.document_type.name].append(ed.page_range)

        # Unverified
        for ud in unverified_docs:
            if ud.suspected_type:
                ranges_by_type[ud.suspected_type].append(ud.page_range)

        # Merge contiguous ranges
        def merge_ranges(ranges):
            parsed = []
            for r in ranges:
                s, e = map(int, r.split("-"))
                parsed.append((s, e))

            parsed.sort()
            merged = []

            for s, e in parsed:
                if not merged or s > merged[-1][1] + 1:
                    merged.append([s, e])
                else:
                    merged[-1][1] = max(merged[-1][1], e)

            return merged

        # Count merged ranges
        counts = {}
        for doc_type, ranges in ranges_by_type.items():
            merged = merge_ranges(ranges)
            counts[doc_type] = len(merged)

        return counts


    @staticmethod
    async def create_document(db: Session, file: UploadFile, user_id: str) -> Document:
        """Create document record in database"""
        status_id = DocumentService.get_status_id_by_code(db, "QUEUED")
        document = Document(
            filename=file.filename,
            original_filename=file.filename,
            file_size=file.size,
            content_type=file.content_type,
            user_id=user_id,
            status_id=status_id
        )
        db.add(document)
        db.commit()
        db.refresh(document)
        return document
    
    @staticmethod
    async def update_document_status(db: Session, document_id: int, status_code: str, 
                                   progress: int = 0, error_message: str = None, 
                                   s3_key: str = None, s3_bucket: str = None):
        """Update document status and notify via WebSocket"""
        document = db.query(Document).filter(Document.id == document_id).first()
        if document:
            status_id = DocumentService.get_status_id_by_code(db, status_code)
            if status_id:
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
                status=status_code,
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
        queued_status_id = DocumentService.get_status_id_by_code(db, "QUEUED")
        if not queued_status_id:
             # Fallback or error? If status missing, we can't create.
             # Assume it exists or use a default?
             # Ideally statuses are seeded.
             pass

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
                status_id=queued_status_id,
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
            
            # Trigger Webhook: document.uploaded
            asyncio.create_task(asyncio.to_thread(
                webhook_service.trigger_webhook_background,
                "document.uploaded",
                {
                    "document_id": document_id,
                    "filename": document.filename,
                    "s3_key": s3_key
                },
                str(document.user_id),
                SessionLocal
            ))
            
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
                    cancelled_status_id = DocumentService.get_status_id_by_code(check_db, "CANCELLED")
                    return current_doc and current_doc.status_id == cancelled_status_id
                finally:
                    check_db.close()

            # Call AI Service
            analysis_result = await ai_service.analyze_document(
                file_bytes, 
                file_data['filename'], 
                schemas,
                db=db,
                document_id=document.id,
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

            # Check if any findings reported an error
            error_findings = [f for f in findings if f.get("type") == "Error" or f.get("type") == "Unknown" and "error" in f.get("data", {})]
            
            if error_findings:
                # If we have errors, mark as AI_FAILED and use the first error message
                first_error = error_findings[0].get("data", {}).get("error", "Unknown AI Error")
                await DocumentService.update_document_status(
                    db, document_id, "AI_FAILED", 
                    progress=100, error_message=f"Partial Analysis Failure: {first_error}"
                )
                
                # Trigger Webhook: document.failed (Partial)
                asyncio.create_task(asyncio.to_thread(
                    webhook_service.trigger_webhook_background,
                    "document.failed",
                    {
                        "document_id": document_id,
                        "filename": document.filename,
                        "error": f"Partial Analysis Failure: {first_error}"
                    },
                    str(document.user_id),
                    SessionLocal
                ))

            else:
                # Final Status - COMPLETED only if no errors
                await DocumentService.update_document_status(
                    db, document_id, "COMPLETED", 
                    progress=100, error_message="Analysis Complete"
                )

                # Trigger Webhook: document.processed
                asyncio.create_task(asyncio.to_thread(
                    webhook_service.trigger_webhook_background,
                    "document.processed",
                    {
                        "document_id": document_id,
                        "filename": document.filename,
                        "status": "COMPLETED"
                    },
                    str(document.user_id),
                    SessionLocal
                ))

        except Exception as e:
            error_str = str(e)
            is_cancelled = "Analysis Cancelled" in error_str
            
            await DocumentService.update_document_status(
                db, document_id, "CANCELLED" if is_cancelled else "AI_FAILED", 
                error_message="Analysis Cancelled" if is_cancelled else error_str
            )

            if not is_cancelled:
                # Trigger Webhook: document.failed
                asyncio.create_task(asyncio.to_thread(
                    webhook_service.trigger_webhook_background,
                    "document.failed",
                    {
                        "document_id": document_id,
                        "filename": (db.query(Document).filter(Document.id == document_id).first()).filename if db.query(Document).filter(Document.id == document_id).first() else "Unknown",
                        "error": error_str
                    },
                    str((db.query(Document).filter(Document.id == document_id).first()).user_id) if db.query(Document).filter(Document.id == document_id).first() else "Unknown",
                    SessionLocal
                ))
            
            print(f"AI Analysis {'Cancelled' if is_cancelled else 'Failed'} for {document_id}: {e}")
        finally:
            db.close()
    
    @staticmethod
    def get_user_documents(db: Session, user_id: str, skip: int = 0, limit: int = 100,
                         status_id: str = None, date_from: str = None, date_to: str = None,
                         search_query: str = None, form_filters: str = None,
                         shared_only: bool = False) -> tuple[List[Document], int]:
        """Get documents for a user with role-based access control"""
        from ..models.document_share import DocumentShare
        # Get user's roles to determine access level - optimized query
        role_names = [r[0] for r in db.query(Role.name).join(UserRole).filter(
            UserRole.user_id == user_id,
            Role.status_id.in_(
                db.query(Status.id).filter(Status.code == 'ACTIVE')
            )
        ).all()]
        is_admin = any(role in ['ADMIN', 'SUPER_ADMIN'] for role in role_names)

        query = db.query(Document)\
            .options(joinedload(Document.form_data_relation))\
            .options(joinedload(Document.status))
        
        if shared_only:
            # ONLY documents shared with the user
            shared_ids = db.query(DocumentShare.document_id).filter(
                DocumentShare.user_id == user_id
            ).subquery()
            query = query.filter(Document.id.in_(shared_ids))
        elif is_admin:
            # Admin users see all documents - no user filter
            pass
        else:
            # Non-admin users see only:
            # 1. Documents they uploaded
            # 2. Documents from clients assigned to them
            # 3. Documents shared with them via DocumentShare
            assigned_client_ids = db.query(UserClient.client_id).filter(
                UserClient.user_id == user_id
            ).subquery()
            
            # Documents shared via DocumentShare
            shared_ids = db.query(DocumentShare.document_id).filter(
                DocumentShare.user_id == user_id
            ).subquery()
            
            # Get documents from assigned clients by joining with form data
            client_documents_query = db.query(Document.id).join(
                DocumentFormData, Document.id == DocumentFormData.document_id
            ).join(
                Client, cast(DocumentFormData.data['client_id'], String) == cast(Client.id, String)
            ).filter(
                Client.id.in_(assigned_client_ids)
            )
            
            query = query.filter(
                or_(
                    Document.user_id == user_id,  # Documents uploaded by user
                    Document.id.in_(client_documents_query),  # Documents from assigned clients
                    Document.id.in_(shared_ids) # Documents shared with user
                )
            )

        # Status Filter (Param status_id is actually the CODE string from frontend e.g. 'UPLOADED')
        if status_id:
            if status_id.upper() == 'ARCHIVED':
                query = query.filter(Document.is_archived == True)
            else:
                query = query.join(Document.status).filter(Status.code == status_id.upper())
                # Also filter out archived documents when showing other statuses
                query = query.filter(Document.is_archived == False)
        else:
            # By default, exclude archived documents
            query = query.filter(Document.is_archived == False)

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

        total_count = query.count()

        documents = query.order_by(Document.created_at.desc())\
            .offset(skip)\
            .limit(limit)\
            .all()
            
        return documents, total_count

    @staticmethod
    def get_document_detail(db: Session, document_id: int, user_id: str) -> Document:
        """Get document with all details (extracted/unverified docs) with role-based access control"""
        from sqlalchemy.orm import joinedload
        from ..models.user import User
        from ..models.user_role import UserRole
        from ..models.role import Role
        from ..models.status import Status
        from ..models.user_client import UserClient
        from ..models.client import Client
        from ..models.document_form_data import DocumentFormData
        from sqlalchemy import cast, String, or_
        
        # Get user's roles to determine access level
        user_roles = db.query(Role.name).join(UserRole).join(User).filter(
            User.id == user_id,
            Role.status_id.in_(
                db.query(Status.id).filter(Status.code == 'ACTIVE')
            )
        ).all()
        
        role_names = [role.name for role in user_roles]
        is_admin = any(role in ['ADMIN', 'SUPER_ADMIN'] for role in role_names)
        
        query = db.query(Document).options(
            joinedload(Document.extracted_documents),
            joinedload(Document.unverified_documents)
        ).filter(Document.id == document_id)
        
        if not is_admin:
            # Non-admin users can only access their own documents or assigned client documents
            assigned_client_ids = db.query(UserClient.client_id).filter(
                UserClient.user_id == user_id
            ).subquery()
            
            client_documents_query = db.query(Document.id).join(
                DocumentFormData, Document.id == DocumentFormData.document_id
            ).join(
                Client, cast(DocumentFormData.data['client_id'], String) == cast(Client.id, String)
            ).filter(
                Client.id.in_(assigned_client_ids)
            )
            
            query = query.filter(
                or_(
                    Document.user_id == user_id,
                    Document.id.in_(client_documents_query)
                )
            )
        
        return query.first()
    
    @staticmethod
    async def archive_document(db: Session, document_id: int, user_id: str) -> bool:
        """Archive a document by setting is_archived to True with role-based access control"""
        from ..models.user import User
        from ..models.user_role import UserRole
        from ..models.role import Role
        from ..models.status import Status
        from ..models.user_client import UserClient
        from ..models.client import Client
        from ..models.document_form_data import DocumentFormData
        from sqlalchemy import cast, String, or_
        
        # Get user's roles to determine access level
        user_roles = db.query(Role.name).join(UserRole).join(User).filter(
            User.id == user_id,
            Role.status_id.in_(
                db.query(Status.id).filter(Status.code == 'ACTIVE')
            )
        ).all()
        
        role_names = [role.name for role in user_roles]
        is_admin = any(role in ['ADMIN', 'SUPER_ADMIN'] for role in role_names)
        
        query = db.query(Document).filter(Document.id == document_id)
        
        if not is_admin:
            assigned_client_ids = db.query(UserClient.client_id).filter(
                UserClient.user_id == user_id
            ).subquery()
            
            client_documents_query = db.query(Document.id).join(
                DocumentFormData, Document.id == DocumentFormData.document_id
            ).join(
                Client, cast(DocumentFormData.data['client_id'], String) == cast(Client.id, String)
            ).filter(
                Client.id.in_(assigned_client_ids)
            )
            
            query = query.filter(
                or_(
                    Document.user_id == user_id,
                    Document.id.in_(client_documents_query)
                )
            )
        
        document = query.first()
        if not document:
            return False
        
        document.is_archived = True
        db.commit()
        
        await websocket_manager.broadcast_document_status(
            document_id=document_id,
            status="ARCHIVED",
            user_id=str(document.user_id),
            progress=100
        )
        return True

    @staticmethod
    async def unarchive_document(db: Session, document_id: int, user_id: str) -> bool:
        """Unarchive a document by setting is_archived to False with role-based access control"""
        from ..models.user import User
        from ..models.user_role import UserRole
        from ..models.role import Role
        from ..models.status import Status
        from ..models.user_client import UserClient
        from ..models.client import Client
        from ..models.document_form_data import DocumentFormData
        from sqlalchemy import cast, String, or_
        
        # Get user's roles to determine access level
        user_roles = db.query(Role.name).join(UserRole).join(User).filter(
            User.id == user_id,
            Role.status_id.in_(
                db.query(Status.id).filter(Status.code == 'ACTIVE')
            )
        ).all()
        
        role_names = [role.name for role in user_roles]
        is_admin = any(role in ['ADMIN', 'SUPER_ADMIN'] for role in role_names)
        
        query = db.query(Document).filter(Document.id == document_id)
        
        if not is_admin:
            assigned_client_ids = db.query(UserClient.client_id).filter(
                UserClient.user_id == user_id
            ).subquery()
            
            client_documents_query = db.query(Document.id).join(
                DocumentFormData, Document.id == DocumentFormData.document_id
            ).join(
                Client, cast(DocumentFormData.data['client_id'], String) == cast(Client.id, String)
            ).filter(
                Client.id.in_(assigned_client_ids)
            )
            
            query = query.filter(
                or_(
                    Document.user_id == user_id,
                    Document.id.in_(client_documents_query)
                )
            )
        
        document = query.first()
        if not document:
            return False
        
        document.is_archived = False
        db.commit()
        
        await websocket_manager.broadcast_document_status(
            document_id=document_id,
            status=document.status.code if document.status else "COMPLETED",
            user_id=str(document.user_id),
            progress=100
        )
        return True

    @staticmethod
    async def delete_document(db: Session, document_id: int, user_id: str) -> Optional[str]:
        """Delete a document and its S3 file with role-based access control"""
        from ..models.user import User
        from ..models.user_role import UserRole
        from ..models.role import Role
        from ..models.status import Status
        from ..models.user_client import UserClient
        from ..models.client import Client
        from ..models.document_form_data import DocumentFormData
        from sqlalchemy import cast, String, or_
        
        # Get user's roles to determine access level
        user_roles = db.query(Role.name).join(UserRole).join(User).filter(
            User.id == user_id,
            Role.status_id.in_(
                db.query(Status.id).filter(Status.code == 'ACTIVE')
            )
        ).all()
        
        role_names = [role.name for role in user_roles]
        is_admin = any(role in ['ADMIN', 'SUPER_ADMIN'] for role in role_names)
        
        query = db.query(Document).filter(Document.id == document_id)
        
        if not is_admin:
            assigned_client_ids = db.query(UserClient.client_id).filter(
                UserClient.user_id == user_id
            ).subquery()
            
            client_documents_query = db.query(Document.id).join(
                DocumentFormData, Document.id == DocumentFormData.document_id
            ).join(
                Client, cast(DocumentFormData.data['client_id'], String) == cast(Client.id, String)
            ).filter(
                Client.id.in_(assigned_client_ids)
            )
            
            query = query.filter(
                or_(
                    Document.user_id == user_id,
                    Document.id.in_(client_documents_query)
                )
            )
        
        document = query.first()
        if not document:
            return None
        
        filename = document.original_filename or document.filename
        
        # Delete from S3 if exists
        if document.s3_key:
            await s3_service.delete_file(document.s3_key)
            
        # Delete analysis report from S3 if exists
        if document.analysis_report_s3_key:
            await s3_service.delete_file(document.analysis_report_s3_key)
        
        # Delete from database
        db.delete(document)
        db.commit()

        # Trigger Webhook: document.deleted
        asyncio.create_task(asyncio.to_thread(
            webhook_service.trigger_webhook_background,
            "document.deleted",
            {
                "document_id": document_id,
                "filename": filename
            },
            str(user_id),
            SessionLocal
        ))
        
        return filename

    @staticmethod
    async def cancel_document_analysis(db: Session, document_id: int, user_id: str):
        """Cancel ongoing analysis by setting status with role-based access control"""
        from ..models.user import User
        from ..models.user_role import UserRole
        from ..models.role import Role
        from ..models.status import Status
        from ..models.user_client import UserClient
        from ..models.client import Client
        from ..models.document_form_data import DocumentFormData
        from sqlalchemy import cast, String, or_
        
        # Get user's roles to determine access level
        user_roles = db.query(Role.name).join(UserRole).join(User).filter(
            User.id == user_id,
            Role.status_id.in_(
                db.query(Status.id).filter(Status.code == 'ACTIVE')
            )
        ).all()
        
        role_names = [role.name for role in user_roles]
        is_admin = any(role in ['ADMIN', 'SUPER_ADMIN'] for role in role_names)
        
        query = db.query(Document).filter(Document.id == document_id)
        
        if not is_admin:
            assigned_client_ids = db.query(UserClient.client_id).filter(
                UserClient.user_id == user_id
            ).subquery()
            
            client_documents_query = db.query(Document.id).join(
                DocumentFormData, Document.id == DocumentFormData.document_id
            ).join(
                Client, cast(DocumentFormData.data['client_id'], String) == cast(Client.id, String)
            ).filter(
                Client.id.in_(assigned_client_ids)
            )
            
            query = query.filter(
                or_(
                    Document.user_id == user_id,
                    Document.id.in_(client_documents_query)
                )
            )
        
        document = query.first()
        if not document:
             return False
             
        await DocumentService.update_document_status(
            db, document_id, "CANCELLED",
            error_message="Analysis Cancelled by User"
        )
        return True

    @staticmethod
    async def reanalyze_document(db: Session, document_id: int, user_id: str):
        """Reset status to AI_QUEUED and trigger background analysis with role-based access control"""
        from ..models.user import User
        from ..models.user_role import UserRole
        from ..models.role import Role
        from ..models.status import Status
        from ..models.user_client import UserClient
        from ..models.client import Client
        from ..models.document_form_data import DocumentFormData
        from sqlalchemy import cast, String, or_
        
        # Get user's roles to determine access level
        user_roles = db.query(Role.name).join(UserRole).join(User).filter(
            User.id == user_id,
            Role.status_id.in_(
                db.query(Status.id).filter(Status.code == 'ACTIVE')
            )
        ).all()
        
        role_names = [role.name for role in user_roles]
        is_admin = any(role in ['ADMIN', 'SUPER_ADMIN'] for role in role_names)
        
        query = db.query(Document).filter(Document.id == document_id)
        
        if not is_admin:
            assigned_client_ids = db.query(UserClient.client_id).filter(
                UserClient.user_id == user_id
            ).subquery()
            
            client_documents_query = db.query(Document.id).join(
                DocumentFormData, Document.id == DocumentFormData.document_id
            ).join(
                Client, cast(DocumentFormData.data['client_id'], String) == cast(Client.id, String)
            ).filter(
                Client.id.in_(assigned_client_ids)
            )
            
            query = query.filter(
                or_(
                    Document.user_id == user_id,
                    Document.id.in_(client_documents_query)
                )
            )
        
        document = query.first()
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

    @staticmethod
    def get_document_stats(db: Session, user_id: str):
        """Get document statistics for a user with role-based access control"""
        from sqlalchemy import func
        from ..models.status import Status
        from ..models.user import User
        from ..models.user_role import UserRole
        from ..models.role import Role
        from ..models.user_client import UserClient
        from ..models.client import Client
        from ..models.document_form_data import DocumentFormData
        from ..models.document_share import DocumentShare
        from ..services.document_share_service import DocumentShareService
        from sqlalchemy import cast, String, or_
        
        # Get user's roles to determine access level
        user_roles = db.query(Role.name).join(UserRole).join(User).filter(
            User.id == user_id,
            Role.status_id.in_(
                db.query(Status.id).filter(Status.code == 'ACTIVE')
            )
        ).all()
        
        role_names = [role.name for role in user_roles]
        is_admin = any(role in ['ADMIN', 'SUPER_ADMIN'] for role in role_names)
        
        # Base query for documents
        base_query = db.query(Document)
        
        if not is_admin:
            # Non-admin users see only their documents and assigned client documents
            assigned_client_ids = db.query(UserClient.client_id).filter(
                UserClient.user_id == user_id
            ).subquery()
            
            client_documents_query = db.query(Document.id).join(
                DocumentFormData, Document.id == DocumentFormData.document_id
            ).join(
                Client, cast(DocumentFormData.data['client_id'], String) == cast(Client.id, String)
            ).filter(
                Client.id.in_(assigned_client_ids)
            )
            
            base_query = base_query.filter(
                or_(
                    Document.user_id == user_id,
                    Document.id.in_(client_documents_query)
                )
            )
        
        # Total active (not archived) documents
        total_active = base_query.filter(
            Document.is_archived == False
        ).count()
        
        # Total archived documents
        total_archived = base_query.filter(
            Document.is_archived == True
        ).count()
        
        # Counts by status
        status_counts = base_query.join(Document.status)\
         .filter(Document.is_archived == False)\
         .with_entities(Status.code, func.count(Document.id))\
         .group_by(Status.code).all()
        
        counts_dict = {code: count for code, count in status_counts}
        
        # Get shared documents count
        share_service = DocumentShareService(db)
        shared_count = share_service.get_shared_documents_count(user_id)
        
        # Aggregated stats for the cards
        return {
            "total": total_active,
            "processed": counts_dict.get("COMPLETED", 0),
            "processing": counts_dict.get("PROCESSING", 0) + counts_dict.get("ANALYZING", 0) + counts_dict.get("AI_QUEUED", 0),
            "sharedWithMe": shared_count,
            "archived": total_archived
        }

document_service = DocumentService()