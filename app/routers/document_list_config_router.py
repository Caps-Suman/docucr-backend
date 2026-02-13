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
        # Determine organisation ID
        org_id = None
        if hasattr(current_user, "organisation_id"):
            org_id = current_user.organisation_id
        elif hasattr(current_user, "id"):
             # Fallback for Organisation object which is its own org
             # Verify it's an organisation by checking table name or just assuming?
             # Given the context, if it doesn't have organisation_id but has id, it's likely the Organisation itself.
             org_id = current_user.id
        
        if not org_id:
             return {"configuration": None}

        configuration = DocumentListConfigService.get_org_config(db, org_id)

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
                
                # If org_id came from current_user.id, it's an Org, so no user_id to track
                track_user_id = current_user.id if hasattr(current_user, "organisation_id") else None
                
                DocumentListConfigService.save_org_config(
                    db, org_id, configuration, track_user_id
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
        # Determine organisation ID
        org_id = None
        if hasattr(current_user, "organisation_id"):
            org_id = current_user.organisation_id
        elif hasattr(current_user, "id"):
             org_id = current_user.id

        if not org_id:
             return {"configuration": None}
             
        configuration = DocumentListConfigService.get_org_config(db, org_id)

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
                
                # If org_id came from current_user.id, it's an Org, so no user_id to track
                track_user_id = current_user.id if hasattr(current_user, "organisation_id") else None
                
                DocumentListConfigService.save_org_config(
                    db, org_id, configuration, track_user_id
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

        # Determine organisation ID
        org_id = None
        if hasattr(current_user, "organisation_id"):
            org_id = current_user.organisation_id
        elif hasattr(current_user, "id"):
             org_id = current_user.id

        if not org_id:
            raise HTTPException(status_code=400, detail="User must belong to an organisation to save configuration")

        configuration["columns"] = columns

        # If org_id came from current_user.id, it's an Org, so no user_id to track
        track_user_id = current_user.id if hasattr(current_user, "organisation_id") else None

        saved_config = DocumentListConfigService.save_org_config(
            db, org_id, configuration, track_user_id
        )
        
        ActivityService.log(
            db=db,
            action="UPDATE",
            entity_type="document_list_view_config",
            entity_id=org_id,
            user_id=track_user_id if track_user_id else current_user.id, # Log even if org? ActivityService might need user_id.. if org, maybe use org_id as user_id or None? Assuming ActivityService handles string IDs.
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
        # Determine organisation ID
        org_id = None
        if hasattr(current_user, "organisation_id"):
            org_id = current_user.organisation_id
        elif hasattr(current_user, "id"):
             org_id = current_user.id

        if not org_id:
             return {"message": "No configuration found to delete"}

        deleted = DocumentListConfigService.delete_org_config(db, org_id)
        
        if deleted:
            # If org_id came from current_user.id, it's an Org, so no user_id to track
            track_user_id = current_user.id if hasattr(current_user, "organisation_id") else None

            ActivityService.log(
                db=db,
                action="DELETE",
                entity_type="document_list_view_config",
                entity_id=org_id,
                user_id=track_user_id if track_user_id else current_user.id,
                request=request,
                background_tasks=background_tasks
            )
            return {"message": "Configuration reset to default"}
        else:
            return {"message": "No configuration found to delete"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete configuration: {str(e)}")
