from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, BackgroundTasks, Request
from sqlalchemy.orm import Session
from ..core.database import get_db
from ..core.permissions import Permission
from ..services.openai_document_ai import OpenAIDocumentAI
from ..services.ai_client import openai_client
from ..models.template import Template
from ..models.document_type import DocumentType
from ..services.activity_service import ActivityService
from ..models.user import User
from ..core.security import get_current_user
import os

router = APIRouter( tags=["AI"])


@router.post("/classify-and-extract")
async def classify_and_extract_document(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    permission: bool = Depends(Permission("documents", "CREATE")),
    req: Request = None,
    background_tasks: BackgroundTasks = None
):
    ActivityService.log(
        db,
        action="PROCESS",
        entity_type="document",
        user_id=current_user.id,
        details={"filename": file.filename, "ai_model": os.getenv("OPEN_AI_MODEL", "gpt-4o-mini")},
        request=req,
        background_tasks=background_tasks
    )
    file_bytes = await file.read()

    # Build schemas from DB
    templates = db.query(Template).all()
    doc_types = db.query(DocumentType).all()

    template_map = {str(t.document_type_id): t for t in templates}
    schemas = []

    for dt in doc_types:
        t = template_map.get(str(dt.id))
        if t:
            schemas.append({
                "type_name": dt.name,
                "fields": t.extraction_fields
            })

    ai = OpenAIDocumentAI(
        client=openai_client,
        model=os.getenv("OPEN_AI_MODEL", "gpt-4o-mini")
    )

    try:
        return await ai.analyze(
            file_bytes=file_bytes,
            filename=file.filename,
            schemas=schemas
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
