from sqlalchemy.orm import Session
from typing import List, Dict
from app.models.document_share import DocumentShare
from app.models.document import Document
from app.models.user import User
from fastapi import HTTPException, status

class DocumentShareService:
    def __init__(self, db: Session):
        self.db = db

    def share_documents(self, document_ids: List[int], user_ids: List[str], shared_by: str) -> bool:
        """Share multiple documents with multiple users"""
        try:
            for document_id in document_ids:
                for user_id in user_ids:
                    # Check if already shared
                    existing = self.db.query(DocumentShare).filter(
                        DocumentShare.document_id == document_id,
                        DocumentShare.user_id == user_id
                    ).first()
                    
                    if not existing:
                        share = DocumentShare(
                            document_id=document_id,
                            user_id=user_id,
                            shared_by=shared_by
                        )
                        self.db.add(share)
            
            self.db.commit()
            return True
        except Exception as e:
            self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to share documents: {str(e)}"
            )

    def get_shared_documents_count(self, user_id: str) -> int:
        """Get count of documents shared with a specific user"""
        return self.db.query(DocumentShare).filter(
            DocumentShare.user_id == user_id
        ).count()

    def get_shared_documents(self, user_id: str) -> List[Dict]:
        """Get documents shared with a specific user"""
        shares = self.db.query(DocumentShare).join(Document).filter(
            DocumentShare.user_id == user_id
        ).all()
        
        return [self._format_shared_document(share) for share in shares]

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