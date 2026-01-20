from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from sqlalchemy.orm import Session
from ..core.database import get_db
from ..core.permissions import Permission
from ..services.openai_document_ai import OpenAIDocumentAI
from ..services.ai_client import openai_client
from ..models.template import Template
from ..models.document_type import DocumentType
import os

router = APIRouter( tags=["AI"])


@router.post("/classify-and-extract")
async def classify_and_extract_document(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    permission: bool = Depends(Permission("documents", "CREATE"))
):
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
