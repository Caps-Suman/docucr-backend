from sqlalchemy.orm import Session
from sqlalchemy import func, or_
from typing import Optional, List, Dict, Tuple
import uuid
from datetime import datetime

from app.models.client import Client
from app.models.user_client import UserClient
from app.models.status import Status


class ClientService:
    @staticmethod
    def get_clients(page: int, page_size: int, search: Optional[str], db: Session) -> Tuple[List[Dict], int]:
        skip = (page - 1) * page_size
        query = db.query(Client).filter(Client.deleted_at.is_(None))
        
        if search:
            query = query.filter(
                or_(
                    Client.business_name.ilike(f"%{search}%"),
                    Client.first_name.ilike(f"%{search}%"),
                    Client.last_name.ilike(f"%{search}%"),
                    Client.npi.ilike(f"%{search}%")
                )
            )
        
        total = query.count()
        clients = query.offset(skip).limit(page_size).all()
        
        return [ClientService._format_client(c) for c in clients], total

    @staticmethod
    def get_client_by_id(client_id: str, db: Session) -> Optional[Dict]:
        client = db.query(Client).filter(Client.id == client_id, Client.deleted_at.is_(None)).first()
        return ClientService._format_client(client) if client else None

    @staticmethod
    def create_client(client_data: Dict, db: Session) -> Dict:
        active_status = db.query(Status).filter(Status.name == 'ACTIVE').first()
        
        new_client = Client(
            id=str(uuid.uuid4()),
            status_id=active_status.id if active_status else None,
            **client_data
        )
        db.add(new_client)
        db.commit()
        db.refresh(new_client)
        return ClientService._format_client(new_client)

    @staticmethod
    def update_client(client_id: str, client_data: Dict, db: Session) -> Optional[Dict]:
        client = db.query(Client).filter(Client.id == client_id, Client.deleted_at.is_(None)).first()
        if not client:
            return None
        
        for key, value in client_data.items():
            setattr(client, key, value)
        
        db.commit()
        db.refresh(client)
        return ClientService._format_client(client)

    @staticmethod
    def delete_client(client_id: str, db: Session) -> bool:
        client = db.query(Client).filter(Client.id == client_id, Client.deleted_at.is_(None)).first()
        if not client:
            return False
        client.deleted_at = datetime.utcnow()
        db.commit()
        return True

    @staticmethod
    def check_npi_exists(npi: str, exclude_id: Optional[str], db: Session) -> bool:
        query = db.query(Client).filter(Client.npi == npi, Client.deleted_at.is_(None))
        if exclude_id:
            query = query.filter(Client.id != exclude_id)
        return query.first() is not None

    @staticmethod
    def activate_client(client_id: str, db: Session) -> Optional[Dict]:
        client = db.query(Client).filter(Client.id == client_id, Client.deleted_at.is_(None)).first()
        if not client:
            return None
        active_status = db.query(Status).filter(Status.name == 'ACTIVE').first()
        if active_status:
            client.status_id = active_status.id
            db.commit()
            db.refresh(client)
        return ClientService._format_client(client)

    @staticmethod
    def deactivate_client(client_id: str, db: Session) -> Optional[Dict]:
        client = db.query(Client).filter(Client.id == client_id, Client.deleted_at.is_(None)).first()
        if not client:
            return None
        inactive_status = db.query(Status).filter(Status.name == 'INACTIVE').first()
        if inactive_status:
            client.status_id = inactive_status.id
            db.commit()
            db.refresh(client)
        return ClientService._format_client(client)

    @staticmethod
    def assign_clients_to_user(user_id: str, client_ids: List[str], assigned_by: str, db: Session) -> bool:
        db.query(UserClient).filter(UserClient.user_id == user_id).delete()
        for client_id in client_ids:
            user_client = UserClient(
                id=str(uuid.uuid4()),
                user_id=user_id,
                client_id=client_id,
                assigned_by=assigned_by
            )
            db.add(user_client)
        db.commit()
        return True

    @staticmethod
    def get_user_clients(user_id: str, db: Session) -> List[Dict]:
        user_clients = db.query(Client).join(UserClient, Client.id == UserClient.client_id).filter(
            UserClient.user_id == user_id,
            Client.deleted_at.is_(None)
        ).all()
        return [ClientService._format_client(c) for c in user_clients]

    @staticmethod
    def _format_client(client: Client) -> Dict:
        return {
            "id": client.id,
            "business_name": client.business_name,
            "first_name": client.first_name,
            "middle_name": client.middle_name,
            "last_name": client.last_name,
            "npi": client.npi,
            "is_user": client.is_user,
            "type": client.type,
            "status_id": client.status_id,
            "description": client.description,
            "created_at": client.created_at,
            "updated_at": client.updated_at
        }
