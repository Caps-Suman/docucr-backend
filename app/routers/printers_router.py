from fastapi import APIRouter, Depends, HTTPException, status, Request, BackgroundTasks
from app.services.activity_service import ActivityService
from app.models.user import User
from app.core.security import get_current_user
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel

from app.core.database import get_db
from app.services.printer_service import PrinterService
from app.core.permissions import Permission

router = APIRouter()

class PrinterBase(BaseModel):
    name: str
    ip_address: str
    port: int = 9100
    protocol: str = "RAW"
    description: Optional[str] = None
    status: str = "ACTIVE"

class PrinterCreate(PrinterBase):
    pass

class PrinterUpdate(BaseModel):
    name: Optional[str] = None
    ip_address: Optional[str] = None
    port: Optional[int] = None
    protocol: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None

class PrinterResponse(PrinterBase):
    id: str
    class Config:
        from_attributes = True

class ConnectionTestRequest(BaseModel):
    ip_address: str
    port: int

@router.get("/", response_model=List[PrinterResponse])
def get_printers(
    skip: int = 0, 
    limit: int = 100, 
    db: Session = Depends(get_db),
    permission: bool = Depends(Permission("settings", "ADMIN"))
):
    return PrinterService.get_printers(db, skip, limit)

@router.post("/", response_model=PrinterResponse)
def create_printer(
    printer: PrinterCreate, 
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    permission: bool = Depends(Permission("settings", "ADMIN")),
    current_user: User = Depends(get_current_user)
):
    created_printer = PrinterService.create_printer(db, printer.model_dump())
    
    ActivityService.log(
        db=db,
        action="CREATE",
        entity_type="printer",
        entity_id=str(created_printer.id),
        user_id=current_user.id,
        details={"name": created_printer.name, "ip": created_printer.ip_address},
        request=request,
        background_tasks=background_tasks
    )
    
    return created_printer

@router.put("/{printer_id}", response_model=PrinterResponse)
def update_printer(
    printer_id: str, 
    printer: PrinterUpdate, 
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    permission: bool = Depends(Permission("settings", "ADMIN")),
    current_user: User = Depends(get_current_user)
):
    printer_data = printer.model_dump(exclude_unset=True)
    
    # Calculate changes BEFORE update
    changes = {}
    existing_printer = PrinterService.get_printer_by_id(db, printer_id)
    if existing_printer:
        changes = ActivityService.calculate_changes(existing_printer, printer_data)

    updated_printer = PrinterService.update_printer(db, printer_id, printer_data)
    if not updated_printer:
        raise HTTPException(status_code=404, detail="Printer not found")
        
    ActivityService.log(
        db=db,
        action="UPDATE",
        entity_type="printer",
        entity_id=printer_id,
        user_id=current_user.id,
        details={"name": updated_printer.name, "changes": changes},
        request=request,
        background_tasks=background_tasks
    )
    
    return updated_printer

@router.delete("/{printer_id}")
def delete_printer(
    printer_id: str, 
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    permission: bool = Depends(Permission("settings", "ADMIN")),
    current_user: User = Depends(get_current_user)
):
    """Delete a printer"""
    name = PrinterService.delete_printer(db, printer_id)
    if not name:
        raise HTTPException(status_code=404, detail="Printer not found")
        
    ActivityService.log(
        db=db,
        action="DELETE",
        entity_type="printer",
        entity_id=printer_id,
        user_id=current_user.id,
        details={"name": name},
        request=request,
        background_tasks=background_tasks
    )
    
    return {"message": "Printer deleted successfully"}

@router.post("/test-connection")
def test_connection_endpoint(
    data: ConnectionTestRequest,
    permission: bool = Depends(Permission("settings", "ADMIN"))
):
    result = PrinterService.test_connection(data.ip_address, data.port)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return result

@router.get("/discover")
def discover_printers(
    db: Session = Depends(get_db),
    permission: bool = Depends(Permission("settings", "ADMIN"))
):
    # Discovery doesn't strictly need DB but we might want to flag already added ones in future
    return PrinterService.discover_printers()

class PrintRequest(BaseModel):
    document_id: int
    copies: int = 1
    color_mode: str = "MONO" # COLOR or MONO
    duplex: bool = False

@router.post("/{printer_id}/print")
async def print_document(
    printer_id: str, 
    print_req: PrintRequest, 
    req_obj: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    permission: bool = Depends(Permission("documents", "READ")),
    current_user: User = Depends(get_current_user)
):
    try:
        await PrinterService.print_document(
            db, 
            printer_id, 
            print_req.document_id,
            copies=print_req.copies,
            color_mode=print_req.color_mode,
            duplex=print_req.duplex
        )
        
        ActivityService.log(
            db=db,
            action="PRINT",
            entity_type="document",
            entity_id=str(print_req.document_id),
            user_id=current_user.id,
            details={
                "printer_id": printer_id, 
                "copies": print_req.copies
            },
            request=req_obj,
            background_tasks=background_tasks
        )
        
        return {"message": "Document sent to printer"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
