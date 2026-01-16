from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List
from pydantic import BaseModel

from app.core.database import get_db
from app.services.privilege_service import PrivilegeService

router = APIRouter()

class PrivilegeResponse(BaseModel):
    id: str
    name: str
    description: str | None

    class Config:
        from_attributes = True

@router.get("", response_model=List[PrivilegeResponse])
@router.get("/", response_model=List[PrivilegeResponse])
async def get_privileges(db: Session = Depends(get_db)):
    privileges = PrivilegeService.get_all_privileges(db)
    return [PrivilegeResponse(**p) for p in privileges]
