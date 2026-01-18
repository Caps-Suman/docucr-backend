from sqlalchemy.orm import Session
from sqlalchemy import func, or_
from typing import Optional, List, Dict, Tuple
import uuid
from datetime import datetime

from app.models.client import Client
from app.models.user import User
from app.models.user_client import UserClient
from app.models.status import Status


class ClientService:
    @staticmethod
    def get_client_stats(db: Session) -> Dict:
        total_clients = db.query(func.count(Client.id)).filter(Client.deleted_at.is_(None)).scalar()
        active_status = db.query(Status).filter(Status.name == 'ACTIVE').first()
        active_clients = db.query(func.count(Client.id)).filter(
            Client.status_id == active_status.id,
            Client.deleted_at.is_(None)
        ).scalar() if active_status else 0
        
        return {
            "total_clients": total_clients,
            "active_clients": active_clients,
            "inactive_clients": total_clients - active_clients
        }

    @staticmethod
    def get_clients(page: int, page_size: int, search: Optional[str], status_id: Optional[str], db: Session) -> Tuple[List[Dict], int]:
        skip = (page - 1) * page_size
        query = db.query(Client).filter(Client.deleted_at.is_(None))
        
        if status_id:
            query = query.filter(Client.status_id == status_id)
        
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
        
        # Extract user_id for linking
        user_id = client_data.get('user_id')
        client_data_copy = client_data.copy()
        client_data_copy.pop('status_id', None)
        
        new_client = Client(
            status_id=active_status.id if active_status else None,
            **client_data_copy
        )
        db.add(new_client)
        db.commit()
        db.refresh(new_client)

        if user_id:
            ClientService._link_user(new_client, user_id, db)

        return ClientService._format_client(new_client)

    @staticmethod
    def _link_user(client: Client, user_id: str, db: Session):
        # Verify user exists
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            # Set direct foreign key relationships
            user.client_id = client.id
            user.is_client = True
            client.is_user = True
            
            # Create UserClient relationship record for many-to-many queries
            user_client = UserClient(
                id=str(uuid.uuid4()),
                client_id=client.id,
                user_id=user_id,
                assigned_by=user_id
            )
            db.add(user_client)
            db.commit()

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
    def deactivate_client(client_id: str, db: Session) -> Optional[Dict]:
        client = db.query(Client).filter(Client.id == client_id, Client.deleted_at.is_(None)).first()
        if not client:
            return None
        
        inactive_status = db.query(Status).filter(Status.name == 'INACTIVE').first()
        if inactive_status:
            client.status_id = inactive_status.id
            
            # Deactivate linked user(s) - Check all possible links
            
            # 1. Direct link on Client
            if client.user_id:
                linked_user = db.query(User).filter(User.id == client.user_id).first()
                if linked_user and not linked_user.is_superuser:
                    linked_user.status_id = inactive_status.id

            # 2. Links via UserClient (Many-to-Many junction)
            linked_users_via_junction = db.query(User).join(UserClient, User.id == UserClient.user_id).filter(
                UserClient.client_id == client.id
            ).all()

            for user in linked_users_via_junction:
                if not user.is_superuser:
                    user.status_id = inactive_status.id

            # 3. Direct link on User (if User.client_id is used)
            linked_users_via_foreign_key = db.query(User).filter(User.client_id == client.id).all()
            for user in linked_users_via_foreign_key:
                if not user.is_superuser:
                    user.status_id = inactive_status.id
            
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
            "id": str(client.id),
            "business_name": client.business_name,
            "first_name": client.first_name,
            "middle_name": client.middle_name,
            "last_name": client.last_name,
            "npi": client.npi,
            "is_user": client.is_user,
            "type": client.type,
            "status_id": client.status_id,
            "description": client.description,
            "created_at": client.created_at.isoformat() if client.created_at else None,
            "updated_at": client.updated_at.isoformat() if client.updated_at else None
        }
