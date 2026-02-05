import re
from fastapi import APIRouter, HTTPException, Depends, Request, BackgroundTasks
from app.models.client import Client
from app.services.activity_service import ActivityService
from app.core.permissions import Permission
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
from datetime import datetime

from app.core.database import get_db
from app.core.security import get_current_user
from app.services.client_service import ClientService
from app.models.user import User
from app.models.user_client import UserClient
from app.models.user_role import UserRole
from app.models.role import Role
from uuid import UUID
import requests
router = APIRouter(dependencies=[Depends(get_current_user)])

@router.get("/npi-lookup/{npi}")
async def npi_lookup(npi: str):
    try:
        response = requests.get(f"https://npiregistry.cms.hhs.gov/api/?version=2.1&number={npi}")
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch NPI details: {str(e)}")

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

    # NEW ADDRESS FIELDS
    address_line_1: Optional[str] = Field(None, max_length=250)
    address_line_2: Optional[str] = Field(None, max_length=250)
    city:Optional[str]=Field(None, min_length=2,max_length=250)
    state_code: Optional[str] = Field(None, min_length=2, max_length=2)
    state_name: Optional[str] = Field(None, max_length=50)
    country: Optional[str] = Field(default="United States", max_length=50)
    zip_code: Optional[str] = Field(
        None,
        description="US ZIP+4 format: 11111-1111"
    )
    @field_validator("zip_code")
    @classmethod
    def validate_zip(cls, v):
        if v is None:
            return v
        if not re.match(r"^[0-9]{5}-[0-9]{4}$", v):
            raise ValueError("ZIP code must be in format 11111-1111")
        return v
   
    @field_validator("address_line_1", "city", "state_code", "zip_code", mode="before")
    @classmethod
    def validate_us_address(cls, v, info):
        data = info.data
        country = data.get("country", "United States")

        if country == "United States" and not v:
            raise ValueError(
                f"{info.field_name} is required for US addresses"
            )
        return v

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

    # NEW ADDRESS FIELDS
    address_line_1: Optional[str] = Field(None, max_length=250)
    address_line_2: Optional[str] = Field(None, max_length=250)
    city:Optional[str]=Field(None, min_length=2,max_length=250)
    state_code: Optional[str] = Field(None, min_length=2, max_length=2)
    state_name: Optional[str] = Field(None, max_length=50)
    country: Optional[str] = Field(None, max_length=50)
    zip_code: Optional[str] = Field(
        None,
        description="US ZIP+4 format: 11111-1111"
    )

    @field_validator("zip_code")
    @classmethod
    def validate_zip(cls, v):
        if v is None:
            return v
        if not re.match(r"^[0-9]{5}-[0-9]{4}$", v):
            raise ValueError("ZIP code must be in format 11111-1111")
        return v
    
    @field_validator("address_line_1", "city", "state_code", "zip_code", mode="before")
    @classmethod
    def validate_us_address(cls, v, info):
        data = info.data
        country = data.get("country", "United States")

        if country == "United States" and not v:
            raise ValueError(
                f"{info.field_name} is required for US addresses"
            )
        return v

class ClientResponse(BaseModel):
    id: UUID
    business_name: Optional[str]
    first_name: Optional[str]
    middle_name: Optional[str]
    last_name: Optional[str]
    npi: Optional[str]
    is_user: bool
    type: Optional[str]
    status_id: Optional[int]
    statusCode: Optional[str] = None
    status_code: Optional[str] = None
    description: Optional[str]
    address_line_1: Optional[str] = Field(None, max_length=250)
    address_line_2: Optional[str] = Field(None, max_length=250)
    city:Optional[str]=Field(None, min_length=2,max_length=250)
    state_code: Optional[str] = Field(None, min_length=2, max_length=2)
    country: Optional[str] = Field(None, max_length=50)
    zip_code: Optional[str] = Field(None, min_length=10, max_length=10)
    # ONLY EXTRA FIELD FOR LIST
    state_name: Optional[str]

    user_count: int = 0
    assigned_users: List[str] = []
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

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

def _is_admin_user(user: User) -> bool:
    role_names = [r.name for r in user.roles]
    return (
        user.is_superuser or
        "ADMIN" in role_names or
        "SUPER_ADMIN" in role_names
    )
class NPICheckRequest(BaseModel):
    npis: List[str]

class NPICheckResponse(BaseModel):
    existing_npis: List[str]

class BulkClientCreateRequest(BaseModel):
    clients: List[ClientCreate]

class BulkClientCreateResponse(BaseModel):
    success: int
    failed: int
    errors: List[str]

@router.get("/stats")
def get_client_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return ClientService.get_client_stats(db, current_user)

@router.get("/visible", response_model=List[ClientResponse])
def get_visible_clients(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    return ClientService.get_visible_clients(db, current_user)

@router.get("/me", response_model=ClientResponse)
async def get_my_client(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # 🔒 Only client users allowed
    if not current_user.client_id:
        raise HTTPException(
            status_code=403,
            detail="This user is not linked to a client"
        )

    client = db.query(Client).filter(
        Client.id == current_user.client_id,
        Client.deleted_at.is_(None)
    ).first()

    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    return ClientResponse(**ClientService._format_client(client, db))

@router.get("", response_model=ClientListResponse)
@router.get("/", response_model=ClientListResponse)
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

class MapUsersRequest(BaseModel):
    user_ids: List[str]
    assigned_by: str

class UnassignUsersToClientRequest(BaseModel):
    user_ids: List[str]

@router.get("/{client_id}/users")
async def get_client_users(client_id: str, db: Session = Depends(get_db)):
    users = db.query(User).join(UserClient, User.id == UserClient.user_id).filter(
        UserClient.client_id == client_id,
        ~db.query(UserRole).join(Role).filter(
            UserRole.user_id == User.id,
            Role.name == 'SUPER_ADMIN'
        ).exists()
    ).all()
    return [{
        "id": user.id, 
        "username": user.username, 
        "name": f"{user.first_name} {user.last_name}",
        "email": user.email,
        "phone_number": user.phone_number,
        # "created_at": user.created_at # Assuming created_at exists on User model, otherwise skip or join UserClient
    } for user in users]

@router.get("/{client_id}", response_model=ClientResponse)
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
    client_data['created_by'] = current_user.id
    created_client = ClientService.create_client(client_data, db, current_user)
    
    ActivityService.log(
        db=db,
        action="CREATE",
        entity_type="client",
        entity_id=str(created_client['id']),
        user_id=current_user.id,
        details={"name": created_client['business_name']},
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
        # Normalize status_id to statusCode for readable logs
        if 'status_id' in client_data and existing_client.get('statusCode'):
            existing_client['status_id'] = existing_client['statusCode']
            
        changes = ActivityService.calculate_changes(existing_client, client_data)
        
        # Rename status_id to Status
        if 'status_id' in changes:
            changes['Status'] = changes.pop('status_id')

    updated_client = ClientService.update_client(client_id, client_data, db)
    if not updated_client:
        raise HTTPException(status_code=404, detail="Client not found")
        
    ActivityService.log(
        db=db,
        action="UPDATE",
        entity_type="client",
        entity_id=client_id,
        user_id=current_user.id,
        details={
            "name": updated_client['business_name'],
            "changes": changes
        },
        request=request,
        background_tasks=background_tasks
    )
        
    return ClientResponse(**updated_client)
@router.post("/{client_id}/activate", response_model=ClientResponse,
             dependencies=[Depends(Permission("clients", "UPDATE"))])
async def activate_client(
    client_id: str,
    db: Session = Depends(get_db),
    request: Request = None,
    background_tasks: BackgroundTasks = None,
    current_user: User = Depends(get_current_user)
):
    # ---- ROLE CHECK ----
    if not _is_admin_user(current_user):
        raise HTTPException(
            status_code=403,
            detail="You are not allowed to activate clients"
        )

    # ---- TARGET VALIDATION ----
    client = ClientService.get_client_by_id(client_id, db)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    # ---- ACTIVATE ----
    updated_client = ClientService.activate_client(client_id, db)
    if not updated_client:
        raise HTTPException(status_code=400, detail="Cannot activate client")

    # ---- LOG ----
    ActivityService.log(
        db=db,
        action="ACTIVATE",
        entity_type="client",
        entity_id=client_id,
        user_id=current_user.id,
        request=request,
        background_tasks=background_tasks
    )

    return ClientResponse(**updated_client)
@router.post("/{client_id}/deactivate", response_model=ClientResponse,
             dependencies=[Depends(Permission("clients", "UPDATE"))])
async def deactivate_client(
    client_id: str,
    db: Session = Depends(get_db),
    request: Request = None,
    background_tasks: BackgroundTasks = None,
    current_user: User = Depends(get_current_user)
):
    # ---- ROLE CHECK ----
    if not _is_admin_user(current_user):
        raise HTTPException(
            status_code=403,
            detail="You are not allowed to deactivate clients"
        )

    # ---- TARGET VALIDATION ----
    client = ClientService.get_client_by_id(client_id, db)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    # ---- DEACTIVATE ----
    updated_client = ClientService.deactivate_client(client_id, db)
    if not updated_client:
        raise HTTPException(status_code=400, detail="Cannot deactivate client")

    # ---- LOG ----
    ActivityService.log(
        db=db,
        action="DEACTIVATE",
        entity_type="client",
        entity_id=client_id,
        user_id=current_user.id,
        request=request,
        background_tasks=background_tasks
    )

    return ClientResponse(**updated_client)

@router.post("/users/{user_id}/assign", dependencies=[Depends(Permission("clients", "ADMIN"))])
async def assign_clients_to_user(user_id: str, request: AssignClientsRequest, db: Session = Depends(get_db)):
    ClientService.assign_clients_to_user(user_id, request.client_ids, request.assigned_by, db)
    return {"message": "Clients assigned successfully"}

@router.post("/{client_id}/users/map", dependencies=[Depends(Permission("clients", "ADMIN"))])
async def map_users_to_client_endpoint(client_id: str, request: MapUsersRequest, db: Session = Depends(get_db)):
    ClientService.map_users_to_client(client_id, request.user_ids, request.assigned_by, db)
    return {"message": "Users mapped successfully"}

@router.post("/{client_id}/users/unassign", dependencies=[Depends(Permission("clients", "ADMIN"))])
async def unassign_users_from_client_endpoint(client_id: str, request: UnassignUsersToClientRequest, db: Session = Depends(get_db)):
    ClientService.unassign_users_from_client(client_id, request.user_ids, db)
    return {"message": "Users unassigned successfully"}

@router.get("/users/{user_id}", response_model=List[ClientResponse])
async def get_user_clients(user_id: str, db: Session = Depends(get_db)):
    clients = ClientService.get_user_clients(user_id, db)
    return [ClientResponse(**client) for client in clients]

@router.post("/check-npis", response_model=NPICheckResponse)
async def check_existing_npis(request: NPICheckRequest, db: Session = Depends(get_db)):
    existing = db.query(Client.npi).filter(
        Client.npi.in_(request.npis),
        Client.deleted_at.is_(None)
    ).all()
    return NPICheckResponse(existing_npis=[n[0] for n in existing if n[0]])

@router.post("/bulk", response_model=BulkClientCreateResponse, dependencies=[Depends(Permission("clients", "CREATE"))])
async def create_clients_bulk(
    request: BulkClientCreateRequest,
    db: Session = Depends(get_db),
    request_obj: Request = None,
    background_tasks: BackgroundTasks = None,
    current_user: User = Depends(get_current_user)
):
    success = 0
    failed = 0
    errors = []
    
    for client_data in request.clients:
        try:
            # Duplicate NPI check
            if client_data.npi and ClientService.check_npi_exists(client_data.npi, None, db):
                failed += 1
                errors.append(f"NPI already exists: {client_data.npi}")
                continue

            client_dict = client_data.model_dump()
            client_dict['created_by'] = current_user.id
            client = ClientService.create_client(client_dict, db)
            if client:
                success += 1
                
                ActivityService.log(
                    db=db,
                    action="CREATE",
                    entity_type="client",
                    entity_id=str(client['id']),
                    user_id=current_user.id,
                    request=request_obj,
                    background_tasks=background_tasks
                )
            else:
                failed += 1
                errors.append(f"Failed to create client with data: {client_data}")
        except Exception as e:
            failed += 1
            errors.append(f"Error creating client: {str(e)}")
    
    return BulkClientCreateResponse(
        success=success,
        failed=failed,
        errors=errors
    )
