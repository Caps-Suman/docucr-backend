from sqlalchemy.orm import Session
from sqlalchemy import func, or_
from typing import Optional, List, Dict, Tuple
import uuid
from datetime import datetime

from app.models.client import Client
from app.models.user import User
from app.models.user_client import UserClient
from app.models.user_role import UserRole
from app.models.role import Role
from app.models.status import Status


class ClientService:
    @staticmethod
    def get_client_stats(db: Session) -> Dict:
        total_clients = db.query(func.count(Client.id)).filter(Client.deleted_at.is_(None)).scalar()
        active_status = db.query(Status).filter(Status.code == 'ACTIVE').first()
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
    def get_clients(page: int, page_size: int, search: Optional[str], status_id: Optional[str], db: Session, current_user: Optional[User] = None) -> Tuple[List[Dict], int]:
        skip = (page - 1) * page_size
        
        # Check if user has admin privileges
        is_admin = False
        if current_user:
            user_roles = [role.name for role in current_user.roles] if hasattr(current_user, 'roles') else []
            is_admin = current_user.is_superuser or 'ADMIN' in user_roles or 'SUPER_ADMIN' in user_roles
        
        if is_admin or not current_user:
            # Admin users see all clients
            query = db.query(Client).filter(Client.deleted_at.is_(None))
        else:
            # Non-admin users see only assigned clients
            query = db.query(Client).join(UserClient, Client.id == UserClient.client_id).filter(
                UserClient.user_id == current_user.id,
                Client.deleted_at.is_(None)
            )
        
        if status_id:
            query = query.join(Client.status_relation).filter(Status.code == status_id)
        
        if search:
            search_term = f"%{search}%"
            query = query.filter(
                or_(
                    Client.business_name.ilike(search_term),
                    Client.first_name.ilike(search_term),
                    Client.last_name.ilike(search_term),
                    Client.npi.ilike(search_term)
                )
            )
        
        total = query.count()
        clients = query.offset(skip).limit(page_size).all()
        
        return [ClientService._format_client(c, db) for c in clients], total

    @staticmethod
    def get_client_by_id(client_id: str, db: Session) -> Optional[Dict]:
        client = db.query(Client).filter(Client.id == client_id, Client.deleted_at.is_(None)).first()
        return ClientService._format_client(client, db) if client else None

    @staticmethod
    def create_client(client_data: Dict, db: Session) -> Dict:
        active_status = db.query(Status).filter(Status.code == 'ACTIVE').first()
        
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

        return ClientService._format_client(new_client, db)

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
            if key == 'status_id' and value is not None:
                # Handle status update safely
                if isinstance(value, str) and not value.isdigit():
                    status_obj = db.query(Status).filter(Status.code == value).first()
                    if status_obj:
                        client.status_id = status_obj.id
                else:
                    client.status_id = value
            elif key != 'status_id':
                setattr(client, key, value)
        
        db.commit()
        db.refresh(client)
        return ClientService._format_client(client, db)

    @staticmethod
    def activate_client(client_id: str, db: Session) -> Optional[Dict]:
        client = db.query(Client).filter(Client.id == client_id, Client.deleted_at.is_(None)).first()
        if not client:
            return None
        
        active_status = db.query(Status).filter(Status.code == 'ACTIVE').first()
        if active_status:
            client.status_id = active_status.id
            db.commit()
            db.refresh(client)
        return ClientService._format_client(client, db)

    @staticmethod
    def deactivate_client(client_id: str, db: Session) -> Optional[Dict]:
        client = db.query(Client).filter(Client.id == client_id, Client.deleted_at.is_(None)).first()
        if not client:
            return None
        
        inactive_status = db.query(Status).filter(Status.code == 'INACTIVE').first()
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
        return ClientService._format_client(client, db)

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
        return [ClientService._format_client(c, db) for c in user_clients]

    @staticmethod
    def check_npi_exists(npi: str, exclude_id: Optional[str], db: Session) -> bool:
        query = db.query(Client).filter(Client.npi == npi, Client.deleted_at.is_(None))
        if exclude_id:
            query = query.filter(Client.id != exclude_id)
        return query.first() is not None

    @staticmethod
    def _format_client(client: Client, db: Session = None) -> Dict:
        status_code = None
        if client.status_id and db:
             status_obj = db.query(Status).filter(Status.id == client.status_id).first()
             if status_obj:
                 status_code = status_obj.code
        elif client.status_id and client.status_relation: # If already eager loaded or available
             status_code = client.status_relation.code

        # Get assigned users (excluding SUPER_ADMIN)
        assigned_users = []
        if db:
            user_assignments = db.query(User).join(UserClient, User.id == UserClient.user_id).filter(
                UserClient.client_id == client.id,
                ~db.query(UserRole).join(Role).filter(
                    UserRole.user_id == User.id,
                    Role.name == 'SUPER_ADMIN'
                ).exists()
            ).all()
            assigned_users = [f"{user.first_name} {user.last_name}" for user in user_assignments]

        return {
            "id": str(client.id),
            "business_name": client.business_name,
            "first_name": client.first_name,
            "middle_name": client.middle_name,
            "last_name": client.last_name,
            "npi": client.npi,
            "is_user": client.is_user,
            "type": client.type,
            "status_id": client.status_id, # Integer
            "statusCode": status_code,     # String
            "description": client.description,
            "assigned_users": assigned_users,
            "created_at": client.created_at.isoformat() if client.created_at else None,
            "updated_at": client.updated_at.isoformat() if client.updated_at else None
        }
