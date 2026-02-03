from fastapi import APIRouter, Depends, HTTPException, Request, BackgroundTasks
from app.services.activity_service import ActivityService
from sqlalchemy.orm import Session
from typing import Dict, Any, List
from pydantic import BaseModel, Field
from ..core.database import get_db
from ..core.security import get_current_user
from ..core.permissions import Permission
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
    db: Session = Depends(get_db),
    permission: bool = Depends(Permission("document_list_view_config", "READ"))
):
    """Get user's document list configuration"""
    try:
        configuration = DocumentListConfigService.get_user_config(db, current_user.id)

        if configuration and "columns" in configuration:
            columns = configuration["columns"]

            existing_ids = {c["id"] for c in columns}
            max_order = max([c["order"] for c in columns], default=0)

            if "pages" not in existing_ids:
                columns.append({
                    "id": "pages",
                    "label": "Pages",
                    "visible": True,
                    "order": max_order + 1,
                    "width": 80,
                    "type": "number",
                    "required": False
                })

                # Persist auto-heal so it doesn't repeat every GET
                configuration["columns"] = columns
                DocumentListConfigService.save_user_config(
                    db, current_user.id, configuration
                )

        return {"configuration": configuration}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve configuration: {str(e)}")

@router.get("/me")
async def get_my_config(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get user's document list configuration without strict permissions"""
    try:
        configuration = DocumentListConfigService.get_config(db)

        if configuration and "columns" in configuration:
            columns = configuration["columns"]

            existing_ids = {c["id"] for c in columns}
            max_order = max([c["order"] for c in columns], default=0)

            if "pages" not in existing_ids:
                columns.append({
                    "id": "pages",
                    "label": "Pages",
                    "visible": True,
                    "order": max_order + 1,
                    "width": 80,
                    "type": "number",
                    "required": False
                })

                # Persist auto-heal so it doesn't repeat every GET
                configuration["columns"] = columns
                DocumentListConfigService.save_user_config(
                    db, current_user.id, configuration
                )

        return {"configuration": configuration}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve configuration: {str(e)}")

@router.put("")
@router.put("/")
async def update_config(
    config_request: DocumentListConfigRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    permission: bool = Depends(Permission("document_list_view_config", "READ"))
):
    """Save or update user's document list configuration"""
    try:
        # Convert to dict for storage
        configuration = config_request.dict()

        # INLINE SYSTEM COLUMN ENFORCEMENT (NO NEW FUNCTIONS)
        columns = configuration.get("columns", [])

        existing_ids = {c["id"] for c in columns}
        max_order = max([c["order"] for c in columns], default=0)

        if "pages" not in existing_ids:
            columns.append({
                "id": "pages",
                "label": "Pages",
                "visible": True,
                "order": max_order + 1,
                "width": 80,
                "type": "number",
                "required": False
            })

        configuration["columns"] = columns


        saved_config = DocumentListConfigService.save_user_config(
            db, current_user.id, configuration
        )
        
        ActivityService.log(
            db=db,
            action="UPDATE",
            entity_type="document_list_view_config",
            entity_id=current_user.id,
            user_id=current_user.id,
            request=request,
            background_tasks=background_tasks
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
    request: Request,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    permission: bool = Depends(Permission("document_list_view_config", "READ"))
):
    """Delete user's document list configuration (reset to default)"""
    try:
        deleted = DocumentListConfigService.delete_user_config(db, current_user.id)
        
        if deleted:
            ActivityService.log(
                db=db,
                action="DELETE",
                entity_type="document_list_view_config",
                entity_id=current_user.id,
                user_id=current_user.id,
                request=request,
                background_tasks=background_tasks
            )
            return {"message": "Configuration reset to default"}
        else:
            return {"message": "No configuration found to delete"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete configuration: {str(e)}")
