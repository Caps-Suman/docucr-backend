from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel

from app.core.database import get_db
from app.services.printer_service import PrinterService

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
def get_printers(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return PrinterService.get_printers(db, skip, limit)

@router.post("/", response_model=PrinterResponse)
def create_printer(printer: PrinterCreate, db: Session = Depends(get_db)):
    return PrinterService.create_printer(db, printer.model_dump())

@router.put("/{printer_id}", response_model=PrinterResponse)
def update_printer(printer_id: str, printer: PrinterUpdate, db: Session = Depends(get_db)):
    updated_printer = PrinterService.update_printer(db, printer_id, printer.model_dump(exclude_unset=True))
    if not updated_printer:
        raise HTTPException(status_code=404, detail="Printer not found")
    return updated_printer

@router.delete("/{printer_id}")
def delete_printer(printer_id: str, db: Session = Depends(get_db)):
    success = PrinterService.delete_printer(db, printer_id)
    if not success:
        raise HTTPException(status_code=404, detail="Printer not found")
    return {"message": "Printer deleted successfully"}

@router.post("/test-connection")
def test_connection_endpoint(data: ConnectionTestRequest):
    result = PrinterService.test_connection(data.ip_address, data.port)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return result

@router.get("/discover")
def discover_printers(db: Session = Depends(get_db)):
    # Discovery doesn't strictly need DB but we might want to flag already added ones in future
    return PrinterService.discover_printers()

class PrintRequest(BaseModel):
    document_id: int
    copies: int = 1
    color_mode: str = "MONO" # COLOR or MONO
    duplex: bool = False

@router.post("/{printer_id}/print")
async def print_document(printer_id: str, request: PrintRequest, db: Session = Depends(get_db)):
    try:
        await PrinterService.print_document(
            db, 
            printer_id, 
            request.document_id,
            copies=request.copies,
            color_mode=request.color_mode,
            duplex=request.duplex
        )
        return {"message": "Document sent to printer"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
