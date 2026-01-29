import secrets
import string
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, List
from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from passlib.hash import pbkdf2_sha256

from app.models.external_share import ExternalShare
from app.models.document import Document
from app.models.user import User
from app.utils.email import send_external_share_email
from app.services.s3_service import s3_service

class ExternalShareService:
    def __init__(self, db: Session):
        self.db = db

    def _generate_token(self, length: int = 32) -> str:
        alphabet = string.ascii_letters + string.digits
        return ''.join(secrets.choice(alphabet) for _ in range(length))

    def create_batch_share(self, document_ids: List[int], email: str, password: str, shared_by: str, expires_in_days: int = 7) -> List[ExternalShare]:
        """Create multiple external share links and send a single summary email."""
        password_hash = pbkdf2_sha256.hash(password)
        expires_at = datetime.now(timezone.utc) + timedelta(days=expires_in_days)
        
        shares = []
        email_docs = []
        
        # RESTRICTION: Recipient must be a registered user
        recipient = self.db.query(User).filter(User.email == email).first()
        if not recipient:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Safety Check: The email '{email}' is not registered. We only allow sharing with internal team members for security."
            )

        try:
            for doc_id in document_ids:
                doc = self.db.query(Document).filter(Document.id == doc_id).first()
                if not doc:
                    continue
                
                token = self._generate_token()
                share = ExternalShare(
                    document_id=doc_id,
                    email=email,
                    password_hash=password_hash,
                    token=token,
                    shared_by=shared_by,
                    expires_at=expires_at
                )
                self.db.add(share)
                shares.append(share)
                
                email_docs.append({
                    "filename": doc.filename,
                    "token": token,
                    "expires_at": expires_at.strftime("%B %d, %Y")
                })
            
            if not shares:
                raise HTTPException(status_code=404, detail="No valid documents found for sharing")
                
            self.db.commit()
            
            # Refresh to get IDs
            for s in shares:
                self.db.refresh(s)
            
            # Send single consolidated email
            send_user = self.db.query(User).filter(User.id == shared_by).first()
            sender_name = f"{send_user.first_name} {send_user.last_name}" if send_user else "A docucr User"
            
            send_external_share_email(
                to_email=email,
                shared_by=sender_name,
                documents=email_docs
            )
            
            return shares
            
        except Exception as e:
            self.db.rollback()
            if isinstance(e, HTTPException):
                raise e
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to create batch external share: {str(e)}"
            )

    def create_share(self, document_id: int, email: str, password: str, shared_by: str, expires_in_days: int = 7) -> ExternalShare:
        """Create a new external share link and send an email."""
        shares = self.create_batch_share([document_id], email, password, shared_by, expires_in_days)
        return shares[0]

    def get_share_by_token(self, token: str) -> ExternalShare:
        """Get share details by token, ensuring it hasn't expired."""
        share = self.db.query(ExternalShare).filter(ExternalShare.token == token).first()
        
        if not share:
            raise HTTPException(status_code=404, detail="Share link not found or invalid")
        
        if share.expires_at < datetime.now(timezone.utc):
            raise HTTPException(status_code=410, detail="Share link has expired")
            
        return share

    def verify_password(self, token: str, password: str) -> bool:
        """Verify the password for a given share token."""
        share = self.get_share_by_token(token)
        return pbkdf2_sha256.verify(password, share.password_hash)

    def get_shared_document_data(self, token: str, password: str) -> Dict:
        """Retrieve document info if password is correct."""
        if not self.verify_password(token, password):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid password")
        
        share = self.get_share_by_token(token)
        doc = share.document
        
        return {
            "id": doc.id,
            "filename": doc.filename,
            "content_type": doc.content_type,
            "status": doc.status.code if doc.status else "UNKNOWN",
            "created_at": doc.created_at.isoformat(),
            "preview_url": self.get_share_links(token, password)["preview_url"],
            "download_url": self.get_share_links(token, password)["download_url"]
        }

    def get_share_links(self, token: str, password: str) -> Dict[str, str]:
        """Generate secure preview and download links for a shared document."""
        share = self.get_share_by_token(token)
        
        if not pbkdf2_sha256.verify(password, share.password_hash):
            raise HTTPException(status_code=401, detail="Invalid password")
            
        doc = share.document
        if not doc or not doc.s3_key:
            raise HTTPException(status_code=404, detail="Document content not found")
            
        # Preview URL (1 hour expiry)
        preview_url = s3_service.generate_presigned_url(doc.s3_key, expiration=3600)
        
        # Download URL with attachment disposition
        filename = doc.original_filename or doc.filename
        disposition = f'attachment; filename="{filename}"'
        download_url = s3_service.generate_presigned_url(
            doc.s3_key, 
            expiration=3600,
            response_content_disposition=disposition
        )
        
        return {
            "preview_url": preview_url,
            "download_url": download_url
        }
