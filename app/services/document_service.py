from fastapi import UploadFile
from datetime import datetime
from typing import List, Optional, Dict, Any, Union
import asyncio
import json
from io import BytesIO
from collections import Counter, defaultdict
from pdfminer.pdfparser import PDFParser
from pdfminer.pdfdocument import PDFDocument
from pdfminer.pdfpage import PDFPage
from PIL import Image

from sqlalchemy import UUID, DateTime, and_, or_, cast, String, select, text, func
from sqlalchemy.orm import Session, joinedload

from app.models.document_share import DocumentShare
from app.models.document_type import DocumentType
from app.models.form import FormField
from app.models.organisation import Organisation

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
from app.models import client

from app.models import user

class DocumentService:
    @staticmethod
    def get_status_id_by_code(db: Session, code: str) -> int:
        status = db.query(Status).filter(Status.code == code).first()
        if status:
            return status.id
        return None
    @staticmethod
    def _get_user_role_flags(user: User):
        role_names = [r.name for r in user.roles]

        return {
            "is_super_admin": "SUPER_ADMIN" in role_names,
            "is_admin": "ADMIN" in role_names,
            "is_client": user.is_client,
            "is_staff": not user.is_client
        }
    # @staticmethod
    # def _document_access_query(db: Session, actor):

    #     base = db.query(Document)

    #     # SUPERADMIN → sees everything
    #     if isinstance(actor, User):
    #         role_names = [r.name for r in actor.roles]
    #         if "SUPER_ADMIN" in role_names:
    #             return base

    #     # -------------------------
    #     # ORGANISATION LOGIN
    #     # -------------------------
    #     if isinstance(actor, Organisation):
    #         return base.filter(
    #             Document.organisation_id == actor.id
    #         )

    #     # -------------------------
    #     # CLIENT USER
    #     # -------------------------
    #     if isinstance(actor, User) and actor.is_client:
    #         return base.filter(
    #             and_(
    #                 Document.client_id == actor.client_id,
    #                 Document.client_id.isnot(None)
    #             )
    #         )

    #     # -------------------------
    #     # STAFF USER
    #     # -------------------------
    #     if isinstance(actor, User) and actor.organisation_id:

    #         assigned_clients = (
    #             db.query(UserClient.client_id)
    #             .filter(UserClient.user_id == actor.id)
    #         )

    #         return base.filter(
    #             or_(
    #                 Document.created_by == actor.id,
    #                 Document.organisation_id == actor.organisation_id,
    #                 Document.client_id.in_(assigned_clients)
    #             )
    #         )

    #     return base.filter(Document.created_by == actor.id)
    @staticmethod
    def _document_access_query(db: Session, actor):

        base = db.query(Document)

        # -----------------------------
        # SUPER ADMIN
        # -----------------------------
        if hasattr(actor, "roles"):
            role_names = [r.name for r in actor.roles]
            if "SUPER_ADMIN" in role_names:
                return base

        # -----------------------------
        # ORG LOGIN
        # actor has no organisation_id but has id
        # -----------------------------
        if hasattr(actor, "is_org") and actor.is_org:
            return base.filter(Document.organisation_id == actor.id)

        # -----------------------------
        # USER INSIDE ORG
        # -----------------------------
        if hasattr(actor, "organisation_id") and actor.organisation_id:

            # client user
            if getattr(actor, "is_client", False):
                return (
                    base
                    .join(User, Document.created_by == User.id)
                    .filter(
                        or_(
                            User.client_id == actor.client_id,
                            User.created_by == actor.id

                            # User.client_id == getattr(actor, "resolved_client_id", actor.client_id),
                            # User.created_by == actor.id
                        )
                    )
                )

            # if getattr(actor, "is_client", False):
            #     return base.filter(Document.client_id == actor.client_id)

            # staff
            assigned_clients = (
                db.query(UserClient.client_id)
                .filter(UserClient.user_id == actor.id)
            )

            return base.filter(
                or_(
                    Document.created_by == actor.id,
                    Document.client_id.in_(assigned_clients),
                )
                # or_(
                #     Document.created_by == actor.id,
                #     Document.organisation_id == actor.organisation_id,
                #     Document.client_id.in_(assigned_clients),
                # )
            )

        # -----------------------------
        # fallback
        # -----------------------------
        if hasattr(actor, "id"):
            return base.filter(Document.created_by == actor.id)

        return base.filter(text("1=0"))




    @staticmethod
    def _get_accessible_document(db: Session, document_id: int, user: User):
        return (
            DocumentService._document_access_query(db, user)
            .filter(Document.id == document_id)
            .first()
        )

    @staticmethod
    def get_total_pages(file_bytes: bytes, content_type: str) -> int:
        try:
            # ---------- PDF ----------
            if content_type == "application/pdf":
                from io import BytesIO
                fp = BytesIO(file_bytes)
                parser = PDFParser(fp)
                doc = PDFDocument(parser)
                return sum(1 for _ in PDFPage.create_pages(doc))

            # ---------- DOCX ----------
            if content_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
                from io import BytesIO
                from docx import Document as DocxDocument
                doc = DocxDocument(BytesIO(file_bytes))

                # Word pages are NOT real pages; this is best-effort
                # Rule: every section break counts as new page
                return max(1, len(doc.sections))

            # ---------- IMAGES ----------
            if content_type in ("image/png", "image/jpeg", "image/jpg"):
                return 1

            # ---------- MULTI-FRAME IMAGES (TIFF) ----------
            if content_type == "image/tiff":
                from io import BytesIO
                img = Image.open(BytesIO(file_bytes))
                return getattr(img, "n_frames", 1)

        except Exception:
            pass

        # Safe fallback
        return 1
    @staticmethod
    def build_derived_document_counts(extracted_docs, unverified_docs):
        """
        Count LOGICAL documents, not pages.
        """

        counts = defaultdict(int)

        # Verified documents
        for ed in extracted_docs:
            if ed.document_type:
                counts[ed.document_type.name] += 1

        # Unverified documents
        for ud in unverified_docs:
            if ud.suspected_type:
                counts[ud.suspected_type] += 1

        return dict(counts)

    @staticmethod
    async def create_document(db: Session, file: UploadFile, user) -> Document:
        status_id = DocumentService.get_status_id_by_code(db, "QUEUED")

        # determine org correctly
        if hasattr(user, "organisation_id") and user.organisation_id:
            org_id = user.organisation_id
        elif user.__class__.__name__ == "Organisation":
            org_id = user.id
        else:
            org_id = None

        document = Document(
            filename=file.filename,
            original_filename=file.filename,
            file_size=file.size,
            content_type=file.content_type,
            created_by=user.id,
            organisation_id=org_id,   # ✅ FIXED
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
                user_id=str(document.created_by),
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
    async def process_multiple_uploads(db: Session, files: List[UploadFile], user: User,                    
                                     enable_ai: bool = False, document_type_id: str = None, 
                                     template_id: str = None, form_id: str = None, form_data: str = None):
        """Create document records immediately and return, process uploads in background"""
        documents = []
        file_buffers = []
        from io import BytesIO
        import json
        from ..models.document_form_data import DocumentFormData
        
        # Create all document records first with QUEUED status
        queued_status_id = DocumentService.get_status_id_by_code(db, "QUEUED")
        if not queued_status_id:
             # Fallback or error? If status missing, we can't create.
             # Assume it exists or use a default?
             # Ideally statuses are seeded.
             pass
        # parsed_form_data = {}
        # extracted_client_id = None

        # if form_data:
        #     try:
        #         parsed_form_data = json.loads(form_data)
        #         extracted_client_id = DocumentService.extract_client_id_from_form_data(
        #             db, parsed_form_data
        #         )
        #     except Exception:
        #         parsed_form_data = {}

        # 🔒 HARD RULE: client users use THEIR client_id only
        # if user.is_client and user.client_id:
        #     client_id = str(user.client_id)
        # else:
        #     client_id = extracted_client_id
        # if user.is_client:
        #     parsed_form_data.pop("client_id", None)
        parsed_form_data = json.loads(form_data) if form_data else {}

        # ============================================
        # AUTO-INJECT DEFAULT VALUES FOR CLIENT USERS
        # ============================================
        if isinstance(user, User) and user.is_client:

            # force client id
            parsed_form_data["client_id"] = str(user.client_id)

            # fetch form fields
            if form_id:
                form_fields = (
                    db.query(FormField)
                    .filter(FormField.form_id ==str(form_id))
                    .all()
                )

                for field in form_fields:
                    label = field.label.lower()

                    # skip client field (already set)
                    if label == "client":
                        continue

                    # provider fields should not come from UI
                    # but defaults must apply
                    if field.default_value is not None:
                        field_key = str(field.id)

                        if field_key not in parsed_form_data:
                            parsed_form_data[field_key] = field.default_value


        # 🔒 HARD LOCK CLIENT USERS
        if isinstance(user, User) and user.is_client:
            client_id_value = user.client_id

            # overwrite form data so UI can't fake it
            parsed_form_data["client_id"] = str(user.client_id)

        else:
            client_id_value = parsed_form_data.get("client_id")



        for file in files:
            # We must buffer the file content because FastAPI closes UploadFile 
            # as soon as the request handler returns.
            content = await file.read()
            file_size = len(content)
            buffer = BytesIO(content)
            total_pages = DocumentService.get_total_pages(content, file.content_type)

            # Reset original file just in case (though we use buffer now)
            await file.seek(0)
            # --------------------------------------------------
            # SINGLE SOURCE OF TRUTH
            # --------------------------------------------------

            if isinstance(user, Organisation):
                created_by = None
                org_id = user.id
                client_id_value = parsed_form_data.get("client_id")

            elif isinstance(user, User):
                created_by = user.id
                org_id = user.organisation_id
                client_id_value = parsed_form_data.get("client_id") or user.client_id

            else:
                raise Exception("Unknown actor")

            document = Document(
                filename=file.filename,
                original_filename=file.filename,
                file_size=file_size,
                content_type=file.content_type,
                created_by=created_by,
                organisation_id=org_id,
                client_id=client_id_value,
                status_id=queued_status_id,
                upload_progress=0,
                enable_ai=enable_ai,
                document_type_id=document_type_id,
                template_id=template_id,
                total_pages=total_pages
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
                user_id=str(document.created_by),
                progress=0
            )
        
        # Start background upload processing (don't await)
        # We pass the buffers instead of the UploadFile objects
        asyncio.create_task(DocumentService._process_uploads_background(
            documents, file_buffers, enable_ai, document_type_id, template_id
        ))
        
        return documents
    # @staticmethod
    # def _visible_documents_query(db, actor):

    #     # ---------------------------------------
    #     # ACTOR = ORGANISATION LOGIN
    #     # ---------------------------------------
    #     if isinstance(actor, Organisation):
    #         base = db.query(Document).filter(
    #             Document.organisation_id == actor.id
    #         )

    #         assigned_clients = (
    #             db.query(UserClient.client_id)
    #             .join(User, UserClient.user_id == User.id)
    #             .filter(User.organisation_id == actor.id)
    #         )

    #         return base.filter(
    #             or_(
    #                 Document.organisation_id == actor.id,
    #                 Document.client_id.in_(assigned_clients)
    #             )
    #         )

    #     # ---------------------------------------
    #     # ACTOR = USER LOGIN
    #     # ---------------------------------------
    #     if isinstance(actor, User):

    #         base = db.query(Document)

    #         role_names = [r.name for r in actor.roles]

    #         # SUPERADMIN
    #         if "SUPER_ADMIN" in role_names:
    #             return base

    #         # CLIENT USER
    #         if actor.is_client:
    #             return base.filter(
    #                 or_(
    #                     Document.client_id == actor.client_id,
    #                     Document.created_by == actor.id
    #                 )
    #             )

    #         # STAFF USER
    #         if actor.organisation_id:
    #             assigned_clients = (
    #                 db.query(UserClient.client_id)
    #                 .filter(UserClient.user_id == actor.id)
    #             )

    #             return base.filter(
    #                 or_(
    #                     Document.created_by == actor.id,
    #                     Document.organisation_id == actor.organisation_id,
    #                     Document.client_id.in_(assigned_clients)
    #                 )
    #             )

    #         # fallback
    #         return base.filter(Document.created_by == actor.id)

    #     raise Exception("Unknown actor")

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
                
                if document and document.created_by:
                     asyncio.run_coroutine_threadsafe(
                        websocket_manager.broadcast_document_status(
                            document_id=document_id,
                            status="UPLOADING",
                            user_id=str(document.created_by),
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
                
            custom_s3_key = f"documents/{document.created_by}/{document_id}_{safe_filename}"

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
                str(document.created_by),
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
                    str(document.created_by),
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
                    str(document.created_by),
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
                    str((db.query(Document).filter(Document.id == document_id).first()).created_by) if db.query(Document).filter(Document.id == document_id).first() else "Unknown",
                    SessionLocal
                ))
            
            print(f"AI Analysis {'Cancelled' if is_cancelled else 'Failed'} for {document_id}: {e}")
        finally:
            db.close()

    @staticmethod
    def get_user_documents(
        db: Session,
        current_user,
        skip: int = 0,
        limit: int = 25,
        status_id=None,
        date_from=None,
        date_to=None,
        search_query=None,
        form_filters=None,
        document_type_id=None,
        client_id=None,
        uploaded_by=None,
        organisation_id=None,
        shared_only=False,
    ):
        from datetime import datetime, timedelta
        from sqlalchemy import and_, func

        # =====================================================
        # BASE QUERY — SINGLE SOURCE OF TRUTH
        # =====================================================
        query = DocumentService._document_access_query(db, current_user)

        query = query.options(joinedload(Document.status))
        query = query.options(joinedload(Document.form_data_relation))

        print('calling for get douc')

        # =====================================================
        # SHARED WITH ME
        # =====================================================
        if shared_only and isinstance(current_user, User):
            query = query.join(
                DocumentShare,
                DocumentShare.document_id == Document.id
            ).filter(
                DocumentShare.user_id == current_user.id
            )

        # =====================================================
        # OPTIONAL FILTERS
        # =====================================================
        if organisation_id:
            query = query.filter(Document.organisation_id == organisation_id)

        if uploaded_by:
            query = query.filter(Document.created_by == uploaded_by)

        if client_id:
            query = query.filter(Document.client_id == client_id)

        # -------------------------
        # STATUS
        # -------------------------
        if status_id:
            code = str(status_id).upper()

            if code == "ARCHIVED":
                query = query.filter(Document.is_archived.is_(True))
            else:
                status = db.query(Status).filter(Status.code == code).first()
                if status:
                    query = query.filter(Document.status_id == status.id)

                query = query.filter(
                    or_(Document.is_archived == False, Document.is_archived.is_(None))
                )

        # -------------------------
        # DOCUMENT TYPE
        # -------------------------
        if document_type_id:
            query = query.filter(Document.document_type_id == document_type_id)

        # -------------------------
        # SEARCH
        # -------------------------
        if search_query:
            query = query.filter(
                Document.original_filename.ilike(f"%{search_query}%")
            )

        # -------------------------
        # DATE FILTERS
        # -------------------------
        if date_from:
            try:
                dt = datetime.fromisoformat(date_from)
                query = query.filter(Document.created_at >= dt)
            except:
                pass

        if date_to:
            try:
                dt = datetime.fromisoformat(date_to)
                query = query.filter(Document.created_at <= dt)
            except:
                pass

        # =====================================================
        # FORM FIELD FILTERS (SAFE CAST)
        # =====================================================
        if form_filters:
            for field_id, value in form_filters.items():
                if not value:
                    continue

                query = query.join(
                    DocumentFormData,
                    DocumentFormData.document_id == Document.id
                )

                # ---- DATE FIELD ----
                if "T" in str(value):
                    try:
                        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
                        start = dt.replace(hour=0, minute=0, second=0, microsecond=0)
                        end = start + timedelta(days=1)

                        query = query.filter(
                            and_(
                                func.nullif(DocumentFormData.data[field_id].astext, "") != None,
                                cast(
                                    func.nullif(DocumentFormData.data[field_id].astext, ""),
                                    DateTime
                                ) >= start,
                                cast(
                                    func.nullif(DocumentFormData.data[field_id].astext, ""),
                                    DateTime
                                ) < end,
                            )
                        )
                    except:
                        pass

                # ---- NORMAL FIELD ----
                else:
                    query = query.filter(
                        DocumentFormData.data[field_id].astext == str(value)
                    )

        # =====================================================
        # TOTAL COUNT
        # =====================================================
        total = query.count()

        # =====================================================
        # PAGINATION
        # =====================================================
        documents = (
            query.order_by(Document.created_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

        if not documents:
            return [], total

        # =====================================================
        # BULK FETCH LOOKUPS
        # =====================================================
        doc_ids = [d.id for d in documents]
        user_ids = {d.created_by for d in documents if d.created_by}
        org_ids = {d.organisation_id for d in documents if d.organisation_id}

        users_map = {
            u.id: u for u in db.query(User).filter(User.id.in_(user_ids)).all()
        }

        org_map = {
            o.id: o for o in db.query(Organisation).filter(Organisation.id.in_(org_ids)).all()
        }

        form_rows = db.query(
            DocumentFormData.document_id,
            DocumentFormData.data
        ).filter(
            DocumentFormData.document_id.in_(doc_ids)
        ).all()

        form_map = {d_id: data for d_id, data in form_rows}

        fields = db.query(FormField).all()
        field_map = {str(f.id): f for f in fields}

        clients = db.query(Client).all()
        client_map = {str(c.id): c for c in clients}

        doc_types = db.query(DocumentType).all()
        doc_type_map = {str(d.id): d for d in doc_types}

        # =====================================================
        # BUILD RESPONSE
        # =====================================================
        result = []

        for doc in documents:
            raw = form_map.get(doc.id, {}) or {}

            # client_name = None
            # doc_type_name = None

            # for field_id, value in raw.items():
            #     field = field_map.get(str(field_id))
            #     if not field or not value:
            #         continue

            #     label = field.label.lower()

            #     if label == "client":
            #         c = client_map.get(str(value))
            #         if c:
            #             client_name = c.business_name or f"{c.first_name} {c.last_name}"
            client_name = None
            doc_type_name = None

            # -----------------------------------
            # 1️⃣ PRIMARY: document.client_id
            # -----------------------------------
            if doc.client_id:
                c = client_map.get(str(doc.client_id))
                if c:
                    client_name = c.business_name or f"{c.first_name} {c.last_name}"

            # -----------------------------------
            # 2️⃣ FALLBACK: form data client field
            # -----------------------------------
            if not client_name:
                for field_id, value in raw.items():
                    field = field_map.get(str(field_id))
                    if not field or not value:
                        continue

                    label = field.label.lower()

                    if label == "client":
                        c = client_map.get(str(value))
                        if c:
                            client_name = c.business_name or f"{c.first_name} {c.last_name}"

                    elif label == "document type":
                        dt = doc_type_map.get(str(value))
                        if dt:
                            doc_type_name = dt.name

            uploaded_by = None
            if doc.created_by and doc.created_by in users_map:
                u = users_map[doc.created_by]
                uploaded_by = f"{u.first_name} {u.last_name}"
            elif doc.organisation_id:
                uploaded_by = "Organisation"

            row = {
                "id": doc.id,
                "filename": doc.filename,
                "original_filename": doc.original_filename,
                "statusCode": doc.status.code if doc.status else None,
                "file_size": doc.file_size,
                "upload_progress": doc.upload_progress,
                "error_message": doc.error_message,
                "total_pages": doc.total_pages,
                "created_at": doc.created_at.isoformat() if doc.created_at else None,
                "updated_at": doc.updated_at.isoformat() if doc.updated_at else None,
                "is_archived": doc.is_archived,
                "uploaded_by": uploaded_by,
                "client": client_name,
                "document_type": doc_type_name,
            }

            if doc.organisation_id in org_map:
                row["organisation_name"] = org_map[doc.organisation_id].name

            result.append(row)

        return result, total



    # @staticmethod
    # def get_document_detail(db: Session, document_id: int, created_by: str, current_user:User) -> Document:
    #     """Get document with all details (extracted/unverified docs) with role-based access control"""
    #     from sqlalchemy.orm import joinedload
    #     from ..models.user import User
    #     from ..models.user_role import UserRole
    #     from ..models.role import Role
    #     from ..models.status import Status
    #     from ..models.user_client import UserClient
    #     from ..models.client import Client
    #     from ..models.document_form_data import DocumentFormData
    #     from sqlalchemy import cast, String, or_
        
    #     # Get user's roles to determine access level
    #     user_roles = db.query(Role.name).join(UserRole).join(User).filter(
    #         User.id == created_by,
    #         Role.status_id.in_(
    #             db.query(Status.id).filter(Status.code == 'ACTIVE')
    #         )
    #     ).all()
        
    #     role_names = [role.name for role in user_roles]
    #     is_admin = any(role in ['ADMIN', 'SUPER_ADMIN'] for role in role_names)
        
    #     query = (
    #         DocumentService._visible_documents_query(db, current_user)
    #         .options(joinedload(Document.extracted_documents))
    #         .options(joinedload(Document.unverified_documents))
    #     )

        
    #     if not is_admin:
    #         query = query.filter(
    #             or_(
    #                 Document.created_by == created_by,
    #                 Document.client_id.in_(
    #                     select(UserClient.client_id).where(UserClient.user_id == created_by)
    #                 )
    #             )
    #         )
    #     return query.filter(Document.id == document_id).first()

    @staticmethod
    def get_document_detail(db: Session, document_id: int, user: User):
        return (
            DocumentService._document_access_query(db, user)
            .options(joinedload(Document.extracted_documents))
            .options(joinedload(Document.unverified_documents))
            .filter(Document.id == document_id)
            .first()
        )

    # @staticmethod
    # async def archive_document(db: Session, document_id: int, created_by: str, current_user:User) -> bool:
    #     """Archive a document by setting is_archived to True with role-based access control"""
    #     from ..models.user import User
    #     from ..models.user_role import UserRole
    #     from ..models.role import Role
    #     from ..models.status import Status
    #     from ..models.user_client import UserClient
    #     from ..models.client import Client
    #     from ..models.document_form_data import DocumentFormData
    #     from sqlalchemy import cast, String, or_
        
    #     # Get user's roles to determine access level
    #     user_roles = db.query(Role.name).join(UserRole).join(User).filter(
    #         User.id == created_by,
    #         Role.status_id.in_(
    #             db.query(Status.id).filter(Status.code == 'ACTIVE')
    #         )
    #     ).all()
        
    #     role_names = [role.name for role in user_roles]
    #     is_admin = any(role in ['ADMIN', 'SUPER_ADMIN'] for role in role_names)
        
    #     query = DocumentService._visible_documents_query(db, current_user)
    #     document = (
    #         DocumentService._visible_documents_query(db, current_user)
    #         .filter(Document.id == document_id)
    #         .first()
    #     )

    #     if not document:
    #         return False

    #     document.is_archived = True
    #     db.commit()
        
    #     await websocket_manager.broadcast_document_status(
    #         document_id=document_id,
    #         status="ARCHIVED",
    #         user_id=str(document.created_by),
    #         progress=100
    #     )
    #     return True
    @staticmethod
    async def archive_document(db: Session, document_id: int, user: User):
        document = DocumentService._get_accessible_document(db, document_id, user)

        if not document:
            return False

        document.is_archived = True
        db.commit()

        await websocket_manager.broadcast_document_status(
            document_id=document_id,
            status="ARCHIVED",
            user_id=str(document.created_by),
            progress=100
        )

        return True

    # @staticmethod
    # async def unarchive_document(db: Session, document_id: int, created_by: str, current_user:User) -> bool:
    #     """Unarchive a document by setting is_archived to False with role-based access control"""
    #     from ..models.user import User
    #     from ..models.user_role import UserRole
    #     from ..models.role import Role
    #     from ..models.status import Status
    #     from ..models.user_client import UserClient
    #     from ..models.client import Client
    #     from ..models.document_form_data import DocumentFormData
    #     from sqlalchemy import cast, String, or_
        
    #     # Get user's roles to determine access level
    #     user_roles = db.query(Role.name).join(UserRole).join(User).filter(
    #         User.id == created_by,
    #         Role.status_id.in_(
    #             db.query(Status.id).filter(Status.code == 'ACTIVE')
    #         )
    #     ).all()
        
    #     role_names = [role.name for role in user_roles]
    #     is_admin = any(role in ['ADMIN', 'SUPER_ADMIN'] for role in role_names)
        
    #     query = DocumentService._visible_documents_query(db, current_user)
    #     document = query.filter(Document.id == document_id).first()

        
    #     if not is_admin:
    #         query = query.filter(
    #             or_(
    #                 Document.created_by == created_by,
    #                 Document.client_id.in_(
    #                     select(UserClient.client_id).where(UserClient.user_id == created_by)
    #                 )
    #             )
    #         )

        
    #     document = query.first()
    #     if not document:
    #         return False
        
    #     document.is_archived = False
    #     db.commit()
        
    #     await websocket_manager.broadcast_document_status(
    #         document_id=document_id,
    #         status=document.status.code if document.status else "COMPLETED",
    #         user_id=str(document.created_by),
    #         progress=100
    #     )
    #     return True
    @staticmethod
    async def unarchive_document(db: Session, document_id: int, user: User):
        document = DocumentService._get_accessible_document(db, document_id, user)

        if not document:
            return False

        document.is_archived = False
        db.commit()

        await websocket_manager.broadcast_document_status(
            document_id=document_id,
            status="UNARCHIVED",
            user_id=str(document.created_by),
            progress=100
        )

        return True


    # @staticmethod
    # async def delete_document(db: Session, document_id: int, created_by: str, current_user:User) -> Optional[str]:
    #     """Delete a document and its S3 file with role-based access control"""
    #     from ..models.user import User
    #     from ..models.user_role import UserRole
    #     from ..models.role import Role
    #     from ..models.status import Status
    #     from ..models.user_client import UserClient
    #     from ..models.client import Client
    #     from ..models.document_form_data import DocumentFormData
    #     from sqlalchemy import cast, String, or_
        
    #     # Get user's roles to determine access level
    #     user_roles = db.query(Role.name).join(UserRole).join(User).filter(
    #         User.id == created_by,
    #         Role.status_id.in_(
    #             db.query(Status.id).filter(Status.code == 'ACTIVE')
    #         )
    #     ).all()
        
    #     role_names = [role.name for role in user_roles]
    #     is_admin = any(role in ['ADMIN', 'SUPER_ADMIN'] for role in role_names)
        
    #     query = DocumentService._visible_documents_query(db, current_user)
    #     document = query.filter(Document.id == document_id).first()

        
    #     if not is_admin:
    #         query = query.filter(
    #             or_(
    #                 Document.created_by == created_by,
    #                 Document.client_id.in_(
    #                     select(UserClient.client_id).where(UserClient.user_id == created_by)
    #                 )
    #             )
    #         )
        
    #     document = query.first()
    #     if not document:
    #         return None
        
    #     filename = document.original_filename or document.filename
        
    #     # Delete from S3 if exists
    #     if document.s3_key:
    #         await s3_service.delete_file(document.s3_key)
            
    #     # Delete analysis report from S3 if exists
    #     if document.analysis_report_s3_key:
    #         await s3_service.delete_file(document.analysis_report_s3_key)
        
    #     # Delete dependent records
    #     from ..models.external_share import ExternalShare
    #     from ..models.document_share import DocumentShare
        
    #     db.query(ExternalShare).filter(ExternalShare.document_id == document_id).delete()
    #     db.query(DocumentShare).filter(DocumentShare.document_id == document_id).delete()

    #     # Delete from database
    #     db.delete(document)
    #     db.commit()

    #     # Trigger Webhook: document.deleted
    #     asyncio.create_task(asyncio.to_thread(
    #         webhook_service.trigger_webhook_background,
    #         "document.deleted",
    #         {
    #             "document_id": document_id,
    #             "filename": filename
    #         },
    #         str(created_by),
    #         SessionLocal
    #     ))
        
    #     return filename
    @staticmethod
    async def delete_document(db: Session, document_id: int, user: User):
        document = DocumentService._get_accessible_document(db, document_id, user)

        if not document:
            return None

        filename = document.original_filename or document.filename

        if document.s3_key:
            await s3_service.delete_file(document.s3_key)

        if document.analysis_report_s3_key:
            await s3_service.delete_file(document.analysis_report_s3_key)

        db.delete(document)
        db.commit()

        return filename


    # @staticmethod
    # async def cancel_document_analysis(db: Session, document_id: int, created_by: str, current_user:User):
    #     """Cancel ongoing analysis by setting status with role-based access control"""
    #     from ..models.user import User
    #     from ..models.user_role import UserRole
    #     from ..models.role import Role
    #     from ..models.status import Status
    #     from ..models.user_client import UserClient
    #     from ..models.client import Client
    #     from ..models.document_form_data import DocumentFormData
    #     from sqlalchemy import cast, String, or_
        
    #     # Get user's roles to determine access level
    #     user_roles = db.query(Role.name).join(UserRole).join(User).filter(
    #         User.id == created_by,
    #         Role.status_id.in_(
    #             db.query(Status.id).filter(Status.code == 'ACTIVE')
    #         )
    #     ).all()
        
    #     role_names = [role.name for role in user_roles]
    #     is_admin = any(role in ['ADMIN', 'SUPER_ADMIN'] for role in role_names)
    #     query = DocumentService._visible_documents_query(db, current_user)
    #     document = query.filter(Document.id == document_id).first()
        
    #     if not is_admin:
    #         query = query.filter(
    #             or_(
    #                 Document.created_by == created_by,
    #                 Document.client_id.in_(
    #                     select(UserClient.client_id).where(UserClient.user_id == created_by)
    #                 )
    #             )
    #         )

        
    #     document = query.first()
    #     if not document:
    #          return False
             
    #     await DocumentService.update_document_status(
    #         db, document_id, "CANCELLED",
    #         error_message="Analysis Cancelled by User"
    #     )
    #     return True
    @staticmethod
    async def cancel_document_analysis(db: Session, document_id: int, user: User):
        document = DocumentService._get_accessible_document(db, document_id, user)

        if not document:
            return False

        await DocumentService.update_document_status(
            db, document_id, "CANCELLED",
            error_message="Cancelled by user"
        )

        return True


    # @staticmethod
    # async def reanalyze_document(db: Session, document_id: int, created_by: str,  current_user:User):
    #     """Reset status to AI_QUEUED and trigger background analysis with role-based access control"""
    #     from ..models.user import User
    #     from ..models.user_role import UserRole
    #     from ..models.role import Role
    #     from ..models.status import Status
    #     from ..models.user_client import UserClient
    #     from ..models.client import Client
    #     from ..models.document_form_data import DocumentFormData
    #     from sqlalchemy import cast, String, or_
        
    #     # Get user's roles to determine access level
    #     user_roles = db.query(Role.name).join(UserRole).join(User).filter(
    #         User.id == created_by,
    #         Role.status_id.in_(
    #             db.query(Status.id).filter(Status.code == 'ACTIVE')
    #         )
    #     ).all()
        
    #     role_names = [role.name for role in user_roles]
    #     is_admin = any(role in ['ADMIN', 'SUPER_ADMIN'] for role in role_names)
        
    #     query = DocumentService._visible_documents_query(db, current_user)
    #     document = query.filter(Document.id == document_id).first()

        
    #     if not is_admin:
    #         query = query.filter(
    #             or_(
    #                 Document.created_by == created_by,
    #                 Document.client_id.in_(
    #                     select(UserClient.client_id).where(UserClient.user_id == created_by)
    #                 )
    #             )
    #         )

    #     document = query.first()
    #     if not document:
    #         raise Exception("Document not found")
            
    #     # We need the S3 file to be present
    #     if not document.s3_key:
    #          raise Exception("Cannot re-analyze: Original file not found on S3")

    #     # Reset status immediately to give instant feedback
    #     await DocumentService.update_document_status(
    #          db, document_id, "AI_QUEUED", 
    #          progress=0, error_message="Queued for Re-analysis"
    #     )

    #     # Spawn background task for the heavy lifting (S3 download + AI)
    #     asyncio.create_task(DocumentService._perform_reanalysis_background(document_id, created_by))
        
    #     return True
    @staticmethod
    async def reanalyze_document(db: Session, document_id: int, user: User):
        document = DocumentService._get_accessible_document(db, document_id, user)

        if not document:
            raise Exception("Not allowed")

        if not document.s3_key:
            raise Exception("No file found")

        await DocumentService.update_document_status(
            db, document_id, "AI_QUEUED",
            progress=0,
            error_message="Reanalysis queued"
        )

        asyncio.create_task(
            DocumentService._perform_reanalysis_background(document_id, user.id)
        )

        return True

    @staticmethod
    async def _perform_reanalysis_background(document_id: int, created_by: str):
        """Background task for re-analysis: Download from S3 -> Start AI"""
        from ..core.database import SessionLocal
        import io
        
        db = SessionLocal()
        try:
            document = db.query(Document).filter(
                Document.id == document_id,
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

    # @staticmethod
    # def get_document_stats(db: Session, created_by: str, current_user: User) -> dict:
    #     """Get document statistics for a user with role-based access control"""
    #     from sqlalchemy import func
    #     from ..models.status import Status
    #     from ..models.user import User
    #     from ..models.user_role import UserRole
    #     from ..models.role import Role
    #     from ..models.user_client import UserClient
    #     from ..models.client import Client
    #     from ..models.document_form_data import DocumentFormData
    #     from ..models.document_share import DocumentShare
    #     from ..services.document_share_service import DocumentShareService
    #     from sqlalchemy import cast, String, or_\
        
    #     base = DocumentService._visible_documents_query(  
    #     db=db,
    #     user=current_user)

    #     total_active = base.filter(Document.is_archived == False).count()
    #     total_archived = base.filter(Document.is_archived == True).count()

    #     status_counts = (
    #         base.join(Document.status)
    #         .filter(Document.is_archived == False)
    #         .with_entities(Status.code, func.count(Document.id))
    #         .group_by(Status.code)
    #         .all()
    #     )

    #     counts = {code: count for code, count in status_counts}

    #     shared_with_me = (
    #         base.join(DocumentShare, DocumentShare.document_id == Document.id)
    #         .filter(DocumentShare.user_id == created_by)
    #         .count()
    #     )

    #     return {
    #         "total": total_active,
    #         "processed": counts.get("COMPLETED", 0),
    #         "processing": (
    #             counts.get("PROCESSING", 0)
    #             + counts.get("ANALYZING", 0)
    #             + counts.get("AI_QUEUED", 0)
    #         ),
    #         "sharedWithMe": shared_with_me,
    #         "archived": total_archived,
    #     }
    @staticmethod
    def get_document_stats(db: Session, user):

        base = DocumentService._document_access_query(db, user)

        total_all = base.count()
        total_archived = base.filter(Document.is_archived == True).count()

        status_counts = (
            base.join(Status, Status.id == Document.status_id)
            .filter(or_(Document.is_archived == False, Document.is_archived.is_(None)))
            .with_entities(Status.code, func.count(Document.id))
            .group_by(Status.code)
            .all()
        )

        counts = {code: count for code, count in status_counts}

        shared_with_me = 0
        if isinstance(user, User):
            shared_with_me = (
                db.query(DocumentShare)
                .join(Document, Document.id == DocumentShare.document_id)
                .filter(DocumentShare.user_id == user.id)
                .count()
            )

        return {
            "total": total_all,  # 🔥 includes archived
            "processed": counts.get("COMPLETED", 0),
            "processing": (
                counts.get("PROCESSING", 0)
                + counts.get("ANALYZING", 0)
                + counts.get("AI_QUEUED", 0)
                + counts.get("UPLOADING", 0)
            ),
            "sharedWithMe": shared_with_me,
            "archived": total_archived,
        }

        # Get user's roles to determine access level
        # user_roles = db.query(Role.name).join(UserRole).join(User).filter(
        #     User.id == user_id,
        #     Role.status_id.in_(
        #         db.query(Status.id).filter(Status.code == 'ACTIVE')
        #     )
        # ).all()
        
        # role_names = [role.name for role in user_roles]
        # is_admin = any(role in ['ADMIN', 'SUPER_ADMIN'] for role in role_names)
        
        # # Base query for documents
        # base_query = db.query(Document)
        
        # if not is_admin:
        #     # Non-admin users see only their documents and assigned client documents
        #     # assigned_client_ids = db.query(UserClient.client_id).filter(
        #     #     UserClient.user_id == user_id
        #     # ).subquery()
        #     assigned_client_ids = select(UserClient.client_id).where(
        #         UserClient.user_id == user_id
        #     )
        #     client_documents_query = db.query(Document.id).join(
        #         DocumentFormData, Document.id == DocumentFormData.document_id
        #     ).join(
        #         Client, cast(DocumentFormData.data['client_id'], String) == cast(Client.id, String)
        #     ).filter(
        #         Client.id.in_(assigned_client_ids)
        #     )
            
        #     base_query = base_query.filter(
        #         or_(
        #             Document.user_id == user_id,
        #             Document.id.in_(client_documents_query)
        #         )
        #     )
        
        # # Total active (not archived) documents
        # total_active = base_query.filter(
        #     Document.is_archived == False
        # ).count()
        
        # # Total archived documents
        # total_archived = base_query.filter(
        #     Document.is_archived == True
        # ).count()
        
        # # Counts by status
        # status_counts = base_query.join(Document.status)\
        #  .filter(Document.is_archived == False)\
        #  .with_entities(Status.code, func.count(Document.id))\
        #  .group_by(Status.code).all()
        
        # counts_dict = {code: count for code, count in status_counts}
        
        # # Get shared documents count
        # share_service = DocumentShareService(db)
        # shared_count = share_service.get_shared_documents_count(user_id)
        
        # # Aggregated stats for the cards
        # return {
        #     "total": total_active,
        #     "processed": counts_dict.get("COMPLETED", 0),
        #     "processing": counts_dict.get("PROCESSING", 0) + counts_dict.get("ANALYZING", 0) + counts_dict.get("AI_QUEUED", 0),
        #     "sharedWithMe": shared_count,
        #     "archived": total_archived
        # }

document_service = DocumentService()