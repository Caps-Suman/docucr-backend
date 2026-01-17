from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from typing import List, Optional, Dict
from app.models.document_type import DocumentType
from fastapi import HTTPException, status

class DocumentTypeService:
    def __init__(self, db: Session):
        self.db = db

    def get_all(self) -> List[Dict]:
        """Get all document types"""
        document_types = self.db.query(DocumentType).all()
        return [{
            "id": str(dt.id),
            "name": dt.name,
            "description": dt.description,
            "status_id": dt.status_id,
            "created_at": dt.created_at.isoformat(),
            "updated_at": dt.updated_at.isoformat()
        } for dt in document_types]

    def get_by_id(self, document_type_id: str) -> Dict:
        """Get document type by ID"""
        document_type = self.db.query(DocumentType).filter(DocumentType.id == document_type_id).first()
        if not document_type:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document type not found"
            )
        return {
            "id": str(document_type.id),
            "name": document_type.name,
            "description": document_type.description,
            "status_id": document_type.status_id,
            "created_at": document_type.created_at.isoformat(),
            "updated_at": document_type.updated_at.isoformat()
        }

    def create(self, name: str, description: Optional[str] = None, status_id: str = 'active') -> Dict:
        """Create a new document type"""
        # Check for case-sensitive duplicate
        existing = self.db.query(DocumentType).filter(DocumentType.name == name).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Document type with this name already exists"
            )
        
        try:
            document_type = DocumentType(name=name, description=description, status_id=status_id)
            self.db.add(document_type)
            self.db.commit()
            self.db.refresh(document_type)
            return {
                "id": str(document_type.id),
                "name": document_type.name,
                "description": document_type.description,
                "status_id": document_type.status_id,
                "created_at": document_type.created_at.isoformat(),
                "updated_at": document_type.updated_at.isoformat()
            }
        except IntegrityError:
            self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Document type with this name already exists"
            )

    def update(self, document_type_id: str, name: Optional[str] = None, description: Optional[str] = None, status_id: Optional[str] = None) -> Dict:
        """Update a document type"""
        document_type = self.db.query(DocumentType).filter(DocumentType.id == document_type_id).first()
        if not document_type:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document type not found"
            )
        
        # Check for case-sensitive duplicate when updating name
        if name is not None and name != document_type.name:
            existing = self.db.query(DocumentType).filter(
                DocumentType.name == name,
                DocumentType.id != document_type_id
            ).first()
            if existing:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Document type with this name already exists"
                )
        
        try:
            if name is not None:
                document_type.name = name
            if description is not None:
                document_type.description = description
            if status_id is not None:
                document_type.status_id = status_id
            
            self.db.commit()
            self.db.refresh(document_type)
            return {
                "id": str(document_type.id),
                "name": document_type.name,
                "description": document_type.description,
                "status_id": document_type.status_id,
                "created_at": document_type.created_at.isoformat(),
                "updated_at": document_type.updated_at.isoformat()
            }
        except IntegrityError:
            self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Document type with this name already exists"
            )

    def activate(self, document_type_id: str) -> Dict:
        """Activate a document type"""
        return self.update(document_type_id, status_id='active')

    def deactivate(self, document_type_id: str) -> Dict:
        """Deactivate a document type"""
        return self.update(document_type_id, status_id='inactive')