from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr

from app.core.database import get_db
from app.services.migration_service import MigrationService

router = APIRouter(prefix="/api/migration", tags=["migration"])

class MigrationRequest(BaseModel):
    super_admin_email: EmailStr
    super_admin_password: str

@router.post("/initialize")
async def initialize_system(request: MigrationRequest, db: Session = Depends(get_db)):
    """
    Initializes the system with default modules, privileges, roles, and a super admin user.
    """
    try:
        result = MigrationService.initialize_system(
            db, 
            request.super_admin_email, 
            request.super_admin_password
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/initialize-printers")
async def initialize_printers(db: Session = Depends(get_db)):
    """
    Initializes the printer table in the database.
    """
    try:
        result = MigrationService.initialize_printer_table(db)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/initialize-activity-logs")
async def initialize_activity_logs(db: Session = Depends(get_db)):
    """
    Initializes the activity_log table in the database.
    """
    try:
        result = MigrationService.initialize_activity_log_table(db)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
