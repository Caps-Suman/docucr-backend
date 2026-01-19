from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List

from app.core.database import get_db
from app.services.status_service import StatusService

router = APIRouter()

class StatusResponse(BaseModel):
    id: int
    code: str
    description: Optional[str]
    type: Optional[str]
    
    class Config:
        from_attributes = True

@router.get("", response_model=List[StatusResponse])
@router.get("/", response_model=List[StatusResponse])
def get_statuses(db: Session = Depends(get_db)):
    statuses = StatusService.get_all_statuses(db)
    return [StatusResponse(**s) for s in statuses]
