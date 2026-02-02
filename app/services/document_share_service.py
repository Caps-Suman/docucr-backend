from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import os
import smtplib
from sqlalchemy import or_
from sqlalchemy.orm import Session
from typing import List, Dict
from app.models.document_share import DocumentShare
from app.models.document import Document
from app.models.user import User
from fastapi import HTTPException, status

class DocumentShareService:
    def __init__(self, db: Session):
        self.db = db    

    @staticmethod
    def apply_shared_access(query, current_user, db: Session):
        shared_doc_ids = (
            db.query(DocumentShare.document_id)
            .filter(DocumentShare.user_id == current_user.id)
            .subquery()
        )

        return query.filter(
            or_(
                Document.user_id == current_user.id,
                Document.id.in_(shared_doc_ids)
            )
        )
    @staticmethod
    def send_internal_share_email(to_email: str, shared_by: str, document_count: int):
        smtp_server = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
        smtp_port = int(os.getenv('SMTP_PORT', 587))
        smtp_username = os.getenv('SMTP_USERNAME')
        smtp_password = os.getenv('SMTP_PASSWORD')
        sender_email = os.getenv('SENDER_EMAIL', smtp_username)
        site_url = os.getenv('FRONTEND_URL', 'http://localhost:3000')

        if not smtp_username or not smtp_password:
            print(f"SMTP not configured. Skipping email to {to_email}")
            return False

        try:
            subject = "Documents shared with you"

            body = f"""
            <p>Hello,</p>
            <p>{shared_by} has shared <strong>{document_count}</strong> document(s) with you.</p>
            <p>Please log in to view them:</p>
            <p><a href="{site_url}">{site_url}</a></p>
            <p>This is an internal notification. Do not forward this email.</p>
            """

            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = f"docucr <{sender_email}>"
            msg["To"] = to_email
            msg.attach(MIMEText(body, "html"))

            with smtplib.SMTP(smtp_server, smtp_port) as server:
                server.starttls()
                server.login(smtp_username, smtp_password)
                server.sendmail(sender_email, to_email, msg.as_string())

            return True
        except Exception as e:
            print(f"Failed to send internal share email: {e}")
            return False

    def share_documents(
        self,
        document_ids: List[int],
        user_ids: List[str],
        shared_by: str
    ) -> int:
        # Validate users
        users = self.db.query(User).filter(User.id.in_(user_ids)).all()
        if len(users) != len(set(user_ids)):
            raise HTTPException(
                status_code=400,
                detail="One or more users do not exist"
            )

        # Validate documents
        documents = self.db.query(Document).filter(
            Document.id.in_(document_ids)
        ).all()
        if len(documents) != len(set(document_ids)):
            raise HTTPException(
                status_code=404,
                detail="One or more documents not found"
            )

        created = 0

        for doc in documents:
            for user in users:
                if user.id == shared_by:
                    continue

                exists = self.db.query(DocumentShare).filter(
                    DocumentShare.document_id == doc.id,
                    DocumentShare.user_id == user.id
                ).first()

                if exists:
                    continue

                self.db.add(
                    DocumentShare(
                        document_id=doc.id,
                        user_id=user.id,
                        shared_by=shared_by
                    )
                )
                created += 1

        self.db.commit()

        # 🔔 SEND EMAILS (AFTER COMMIT)
        sharer = self.db.query(User).filter(User.id == shared_by).first()
        sharer_name = (
            f"{sharer.first_name} {sharer.last_name}".strip()
            if sharer else "A colleague"
        )

        for user in users:
            self.send_internal_share_email(
                to_email=user.email,
                shared_by=sharer_name,
                document_count=len(document_ids)
            )

        return created, users


    # -----------------------------
    # Get shared documents
    # -----------------------------
    def get_shared_documents(self, user_id: str) -> List[Document]:
        return (
            self.db.query(Document)
            .join(DocumentShare, Document.id == DocumentShare.document_id)
            .filter(DocumentShare.user_id == user_id)
            .all()
        )

    # -----------------------------
    # Count shared documents
    # -----------------------------
    def get_shared_documents_count(self, user_id: str) -> int:
        return (
            self.db.query(DocumentShare)
            .filter(DocumentShare.user_id == user_id)
            .count()
        )

    def _format_shared_document(self, share: DocumentShare) -> Dict:
        return {
            "id": str(share.document.id),
            "filename": share.document.filename,
            "document_type": share.document.document_type,
            "status": share.document.status,
            "shared_by": share.shared_by,
            "shared_at": share.created_at.isoformat(),
            "created_at": share.document.created_at.isoformat()
        }