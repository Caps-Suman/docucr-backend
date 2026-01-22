from fastapi import APIRouter, HTTPException, Depends, Request, BackgroundTasks
from app.services.activity_service import ActivityService
from app.core.permissions import Permission
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

from app.core.database import get_db
from app.core.security import get_current_user
from app.services.client_service import ClientService
from app.models.user import User
from app.models.user_client import UserClient
from app.models.user_role import UserRole
from app.models.role import Role

router = APIRouter(dependencies=[Depends(get_current_user)])

class ClientCreate(BaseModel):
    business_name: Optional[str] = None
    first_name: Optional[str] = None
    middle_name: Optional[str] = None
    last_name: Optional[str] = None
    npi: Optional[str] = None
    is_user: bool = False
    type: Optional[str] = None
    status_id: Optional[str] = None
    description: Optional[str] = None
    user_id: Optional[str] = None

class ClientUpdate(BaseModel):
    business_name: Optional[str] = None
    first_name: Optional[str] = None
    middle_name: Optional[str] = None
    last_name: Optional[str] = None
    npi: Optional[str] = None
    is_user: Optional[bool] = None
    type: Optional[str] = None
    status_id: Optional[str] = None
    description: Optional[str] = None

class ClientResponse(BaseModel):
    id: str
    business_name: Optional[str]
    first_name: Optional[str]
    middle_name: Optional[str]
    last_name: Optional[str]
    npi: Optional[str]
    is_user: bool
    type: Optional[str]
    status_id: Optional[int]
    statusCode: Optional[str]
    description: Optional[str]
    assigned_users: List[str]
    created_at: Optional[str]
    updated_at: Optional[str]
    
    class Config:
        from_attributes = True

class ClientListResponse(BaseModel):
    clients: List[ClientResponse]
    total: int
    page: int
    page_size: int

class AssignClientsRequest(BaseModel):
    client_ids: List[str]
    assigned_by: str

@router.get("/stats", dependencies=[Depends(Permission("clients", "READ"))])
async def get_client_stats(db: Session = Depends(get_db)):
    return ClientService.get_client_stats(db)

@router.get("", response_model=ClientListResponse, dependencies=[Depends(Permission("clients", "READ"))])
@router.get("/", response_model=ClientListResponse, dependencies=[Depends(Permission("clients", "READ"))])
def get_clients(
    page: int = 1,
    page_size: int = 25,
    search: Optional[str] = None,
    status_id: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    clients, total = ClientService.get_clients(page, page_size, search, status_id, db, current_user)
    return ClientListResponse(
        clients=[ClientResponse(**client) for client in clients],
        total=total,
        page=page,
        page_size=page_size
    )

@router.get("/{client_id}/users", dependencies=[Depends(Permission("clients", "READ"))])
async def get_client_users(client_id: str, db: Session = Depends(get_db)):
    users = db.query(User).join(UserClient, User.id == UserClient.user_id).filter(
        UserClient.client_id == client_id,
        ~db.query(UserRole).join(Role).filter(
            UserRole.user_id == User.id,
            Role.name == 'SUPER_ADMIN'
        ).exists()
    ).all()
    return [{"id": user.id, "username": user.username, "name": f"{user.first_name} {user.last_name}"} for user in users]

@router.get("/{client_id}", response_model=ClientResponse, dependencies=[Depends(Permission("clients", "READ"))])
async def get_client(client_id: str, db: Session = Depends(get_db)):
    client = ClientService.get_client_by_id(client_id, db)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    return ClientResponse(**client)

@router.post("/", response_model=ClientResponse, dependencies=[Depends(Permission("clients", "CREATE"))])
async def create_client(
    client: ClientCreate, 
    db: Session = Depends(get_db), 
    request: Request = None,
    background_tasks: BackgroundTasks = None,
    current_user: User = Depends(get_current_user)
):
    if client.npi and ClientService.check_npi_exists(client.npi, None, db):
        raise HTTPException(status_code=400, detail="NPI already exists")
    
    client_data = client.model_dump()
    created_client = ClientService.create_client(client_data, db)
    
    ActivityService.log(
        db=db,
        action="CREATE",
        entity_type="client",
        entity_id=str(created_client.id),
        user_id=current_user.id,
        details={"name": created_client.business_name},
        request=request,
        background_tasks=background_tasks
    )
    
    return ClientResponse(**created_client)

@router.put("/{client_id}", response_model=ClientResponse, dependencies=[Depends(Permission("clients", "UPDATE"))])
async def update_client(
    client_id: str, 
    client: ClientUpdate, 
    db: Session = Depends(get_db), 
    request: Request = None,
    background_tasks: BackgroundTasks = None,
    current_user: User = Depends(get_current_user)
):
    if client.npi and ClientService.check_npi_exists(client.npi, client_id, db):
        raise HTTPException(status_code=400, detail="NPI already exists")
    
    client_data = client.model_dump(exclude_unset=True)

    # Capture changes
    changes = {}
    existing_client = ClientService.get_client_by_id(client_id, db)
    if existing_client:
        changes = ActivityService.calculate_changes(existing_client, client_data)

    updated_client = ClientService.update_client(client_id, client_data, db)
    if not updated_client:
        raise HTTPException(status_code=404, detail="Client not found")
        
    ActivityService.log(
        db=db,
        action="UPDATE",
        entity_type="client",
        entity_id=client_id,
        user_id=current_user.id,
        details={"name": updated_client.get('business_name'), "changes": changes},
        request=request,
        background_tasks=background_tasks
    )
        
    return ClientResponse(**updated_client)

@router.post("/{client_id}/activate", response_model=ClientResponse, dependencies=[Depends(Permission("clients", "UPDATE"))])
async def activate_client(
    client_id: str, 
    db: Session = Depends(get_db), 
    request: Request = None,
    background_tasks: BackgroundTasks = None,
    current_user: User = Depends(get_current_user)
):
    client = ClientService.activate_client(client_id, db)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
        
    ActivityService.log(
        db=db,
        action="ACTIVATE",
        entity_type="client",
        entity_id=client_id,
        user_id=current_user.id,
        request=request,
        background_tasks=background_tasks
    )
        
    return ClientResponse(**client)

@router.post("/{client_id}/deactivate", response_model=ClientResponse, dependencies=[Depends(Permission("clients", "UPDATE"))])
async def deactivate_client(
    client_id: str, 
    db: Session = Depends(get_db), 
    request: Request = None,
    background_tasks: BackgroundTasks = None,
    current_user: User = Depends(get_current_user)
):
    client = ClientService.deactivate_client(client_id, db)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
        
    ActivityService.log(
        db=db,
        action="DEACTIVATE",
        entity_type="client",
        entity_id=client_id,
        user_id=current_user.id,
        request=request,
        background_tasks=background_tasks
    )
        
    return ClientResponse(**client)

@router.post("/users/{user_id}/assign", dependencies=[Depends(Permission("clients", "ADMIN"))])
async def assign_clients_to_user(user_id: str, request: AssignClientsRequest, db: Session = Depends(get_db)):
    ClientService.assign_clients_to_user(user_id, request.client_ids, request.assigned_by, db)
    return {"message": "Clients assigned successfully"}

@router.get("/users/{user_id}", response_model=List[ClientResponse], dependencies=[Depends(Permission("clients", "READ"))])
async def get_user_clients(user_id: str, db: Session = Depends(get_db)):
    clients = ClientService.get_user_clients(user_id, db)
    return [ClientResponse(**client) for client in clients]
