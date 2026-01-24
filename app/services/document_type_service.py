from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from typing import List, Optional, Dict
from app.models.document_type import DocumentType
from app.models.status import Status
from fastapi import HTTPException, status

class DocumentTypeService:
    def __init__(self, db: Session):
        self.db = db

    def get_all(self) -> List[Dict]:
        """Get all document types"""
        document_types = self.db.query(DocumentType).join(Status).all()
        # return [{
        #     "id": str(dt.id),
        #     "name": dt.name,
        #     "description": dt.description or "",
        #     "status_id": dt.status_id,
        #     "statusCode": dt.status.code if dt.status else "",
        #     "created_at": dt.created_at.isoformat(),
        #     "updated_at": dt.updated_at.isoformat()
        # } for dt in document_types]
        return self.db.query(DocumentType).join(Status).all()


    def get_active(self) -> List[Dict]:
        """Get all active document types"""
        # Find active status by code and get its ID
        active_status = self.db.query(Status).filter(Status.code == 'ACTIVE').first()
        if not active_status:
            # If no active status found, return all document types
            document_types = self.db.query(DocumentType).join(Status).all()
        else:
            # Filter by status ID (foreign key)
            document_types = self.db.query(DocumentType).join(Status).filter(DocumentType.status_id == active_status.id).all()
        query = self.db.query(DocumentType).join(Status)
        if active_status:
            query = query.filter(DocumentType.status_id == active_status.id)
        return query.all()
        # return [{
        #     "id": str(dt.id),
        #     "name": dt.name,
        #     "description": dt.description or "",
        #     "status_id": dt.status_id,
        #     "statusCode": dt.status.code if dt.status else "",
        #     "created_at": dt.created_at.isoformat(),
        #     "updated_at": dt.updated_at.isoformat()
        # } for dt in document_types]


    def get_by_id(self, document_type_id: str) -> Dict:
        """Get document type by ID"""
        document_type = self.db.query(DocumentType).join(Status).filter(DocumentType.id == document_type_id).first()
        if not document_type:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document type not found"
            )
        # return {
        #     "id": str(document_type.id),
        #     "name": document_type.name,
        #     "description": document_type.description or "",
        #     "status_id": document_type.status_id,
        #     "statusCode": document_type.status.code if document_type.status else "",
        #     "created_at": document_type.created_at.isoformat(),
        #     "updated_at": document_type.updated_at.isoformat()
        # }
        return document_type
    def create(self, name: str, description: Optional[str] = None, status_id: Optional[str] = None) -> Dict:
        """Create a new document type"""
        # Handle status_id conversion from code to ID
        if status_id is None or isinstance(status_id, str):
            # If status_id is a string, treat it as a status code
            status_code = status_id if status_id else 'INACTIVE'
            status_obj = self.db.query(Status).filter(Status.code == status_code.upper()).first()
            if not status_obj:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Status '{status_code}' not found in status table"
                )
            status_id = status_obj.id
        
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
            # Need to reload status relationship to get code, or query it
            self.db.refresh(document_type) # force load
            # return {
            #     "id": str(document_type.id),
            #     "name": document_type.name,
            #     "description": document_type.description or "",
            #     "status_id": document_type.status_id,
            #     "statusCode": document_type.status.code if document_type.status else "",
            #     "created_at": document_type.created_at.isoformat(),
            #     "updated_at": document_type.updated_at.isoformat()
            # }
            return document_type
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
        
        # Handle status_id conversion from code to ID
        if status_id is not None and isinstance(status_id, str) and not status_id.isdigit():
            status_obj = self.db.query(Status).filter(Status.code == status_id.upper()).first()
            if not status_obj:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Status '{status_id}' not found in status table"
                )
            status_id = status_obj.id
        
        try:
            if name is not None:
                document_type.name = name
            if description is not None:
                document_type.description = description
            if status_id is not None:
                document_type.status_id = status_id
            
            self.db.commit()
            self.db.refresh(document_type)
            self.db.refresh(document_type)
            # self.db.refresh(document_type, ['status'])
            # return {
            #     "id": str(document_type.id),
            #     "name": document_type.name,
            #     "description": document_type.description or "",
            #     "status_id": document_type.status_id,
            #     "statusCode": document_type.status.code if document_type.status else "",
            #     "created_at": document_type.created_at.isoformat(),
            #     "updated_at": document_type.updated_at.isoformat()
            # }
            return document_type

        except IntegrityError:
            self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Document type with this name already exists"
            )

    def activate(self, document_type_id: str) -> Dict:
        """Activate a document type"""
        active_status = self.db.query(Status).filter(Status.code == 'ACTIVE').first()
        if not active_status:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Active status not found in status table"
            )
        return self.update(document_type_id, status_id=active_status.id)

    def deactivate(self, document_type_id: str) -> Dict:
        """Deactivate a document type"""
        inactive_status = self.db.query(Status).filter(Status.code == 'INACTIVE').first()
        if not inactive_status:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Inactive status not found in status table"
            )
        return self.update(document_type_id, status_id=inactive_status.id)

    def delete(self, document_type_id: str) -> Optional[str]:
        """Delete a document type and all associated templates"""
        document_type = self.db.query(DocumentType).filter(DocumentType.id == document_type_id).first()
        if not document_type:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document type not found"
            )
        
        name = document_type.name
        
        # Delete the document type (templates will be deleted automatically due to cascade)
        self.db.delete(document_type)
        self.db.commit()
        
        return name