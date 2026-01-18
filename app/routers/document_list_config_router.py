from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Dict, Any, List
from pydantic import BaseModel, Field
from ..core.database import get_db
from ..core.security import get_current_user
from ..models.user import User
from ..services.document_list_config_service import DocumentListConfigService

router = APIRouter(prefix="/api/document-list-config", tags=["document-list-config"])

class ColumnConfig(BaseModel):
    id: str
    label: str
    visible: bool
    order: int
    width: int = Field(default=150, ge=50, le=500)
    type: str = Field(default="text")
    required: bool = Field(default=False)

class DocumentListConfigRequest(BaseModel):
    columns: List[ColumnConfig]
    viewportWidth: int = Field(ge=320, le=3840)

@router.get("")
@router.get("/")
async def get_config(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get user's document list configuration"""
    try:
        configuration = DocumentListConfigService.get_user_config(db, current_user.id)
        return {"configuration": configuration}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve configuration: {str(e)}")

@router.put("")
@router.put("/")
async def update_config(
    config_request: DocumentListConfigRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Save or update user's document list configuration"""
    try:
        # Convert to dict for storage
        configuration = config_request.dict()
        
        saved_config = DocumentListConfigService.save_user_config(
            db, current_user.id, configuration
        )
        
        return {
            "message": "Configuration updated successfully", 
            "configuration": saved_config
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save configuration: {str(e)}")

@router.delete("")
@router.delete("/")
async def delete_config(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete user's document list configuration (reset to default)"""
    try:
        deleted = DocumentListConfigService.delete_user_config(db, current_user.id)
        
        if deleted:
            return {"message": "Configuration reset to default"}
        else:
            return {"message": "No configuration found to delete"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete configuration: {str(e)}")
