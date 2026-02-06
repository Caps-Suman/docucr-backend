from sqlalchemy.orm import Session
from sqlalchemy import func, or_, select
from typing import Optional, List, Dict, Tuple
import uuid
from datetime import datetime
from sqlalchemy.dialects.postgresql import insert

from app.models.client import Client
from app.models.client_location import ClientLocation
from app.models.organisation import Organisation
from app.models.provider import Provider # Added this import based on the context of the instruction
from app.models.user import User
from app.models.user_client import UserClient
from app.models.user_role import UserRole
from app.models.role import Role
from app.models.status import Status
from app.services.user_service import UserService
import logging

logger = logging.getLogger(__name__)


class ClientService:

    @staticmethod
    def get_visible_clients(db: Session, current_user):
        # Fetch active status
        active_status = db.query(Status.id).filter(
            Status.code == "ACTIVE"
        ).scalar()

        # Get role names
        role_names = [
            r[0] for r in db.query(Role.name)
            .join(UserRole)
            .filter(UserRole.user_id == current_user.id)
            .all()
        ]

        is_admin = any(r in ["ADMIN", "SUPER_ADMIN"] for r in role_names)
        is_supervisor = "SUPERVISOR" in role_names

        # --- ADMIN: ALL CLIENTS ---
        if is_admin:
            clients = db.query(Client).filter(
                Client.status_id == active_status
            ).order_by(Client.business_name).all()
            return [ClientService._format_client(c, db) for c in clients]

        # --- SUPERVISOR ---
        if is_supervisor:
            # Clients directly assigned to supervisor
            direct_clients = select(UserClient.client_id).where(
                UserClient.user_id == current_user.id
            )

            # Users under supervisor
            subordinate_users = select(UserClient.user_id).where(
                UserClient.supervisor_id == current_user.id
            )

            subordinate_clients = select(UserClient.client_id).where(
                UserClient.user_id.in_(subordinate_users)
            )

            clients = db.query(Client).filter(
                Client.status_id == active_status,
                Client.id.in_(direct_clients.union(subordinate_clients))
            ).order_by(Client.business_name).all()
            return [ClientService._format_client(c, db) for c in clients]

        # --- REGULAR USER / CLIENT ---
        assigned_clients = select(UserClient.client_id).where(
            UserClient.user_id == current_user.id
        )

        clients = db.query(Client).filter(
            Client.status_id == active_status,
            or_(
                Client.id.in_(assigned_clients),
                Client.created_by == current_user.id  # OWNER ACCESS
            )
        ).order_by(Client.business_name).all()


        return [ClientService._format_client(c, db) for c in clients]
    @staticmethod
    def link_client_owner(db: Session, user_id: str, client_id: str):
        user = db.query(User).filter(User.id == user_id).first()
        client = db.query(Client).filter(Client.id == client_id).first()

        if not user or not client:
            raise ValueError("User or Client not found")

        # ---- HARD RULES ----
        if user.client_id and user.client_id != client.id:
            raise ValueError("User already linked to another client")

        if client.created_by and client.created_by != user.id:
            raise ValueError("Client already has an owner")

        # ---- OWNERSHIP ONLY ----
        user.client_id = client.id
        user.is_client = True

        client.created_by = user.id
        client.is_user = True

        db.commit()
 
    @staticmethod
    def get_client_stats(db: Session, current_user: User) -> Dict:
        # Detect admin
        user_roles = [role.name for role in current_user.roles]
        is_admin = (
            current_user.is_superuser or
            'ADMIN' in user_roles or
            'SUPER_ADMIN' in user_roles
        )

        base_query = db.query(Client).filter(Client.deleted_at.is_(None))

        if not is_admin:
            base_query = base_query.join(
                UserClient, Client.id == UserClient.client_id
            ).filter(
                UserClient.user_id == current_user.id
            )

        total_clients = base_query.count()

        active_status = db.query(Status).filter(Status.code == 'ACTIVE').first()
        inactive_status = db.query(Status).filter(Status.code == 'INACTIVE').first()

        active_clients = base_query.filter(
            Client.status_id == active_status.id
        ).count() if active_status else 0

        inactive_clients = base_query.filter(
            Client.status_id == inactive_status.id
        ).count() if inactive_status else 0

        return {
            "total_clients": total_clients,
            "active_clients": active_clients,
            "inactive_clients": inactive_clients
        }

    @staticmethod
    def get_clients(page: int, page_size: int, search: Optional[str], status_id: Optional[str], db: Session, current_user: Optional[User] = None) -> Tuple[List[Dict], int]:
        skip = (page - 1) * page_size
        
        query = db.query(Client).filter(Client.deleted_at.is_(None))
        
        # if current_user and not current_user.is_superuser:
        #     query = query.filter(Client.created_by == current_user.id)
        if not current_user.is_superuser:
            if getattr(current_user, 'is_client', False):
                query = query.filter(Client.created_by == str(current_user.id))
            else:
                 query = query.filter(Client.organisation_id == str(current_user.id))
        
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
        clients = query.order_by(Client.created_at.desc()).offset(skip).limit(page_size).all()
        
        return [ClientService._format_client(c, db, detailed=False) for c in clients], total

    # @staticmethod
    # def create_client(client_data: Dict, db: Session, current_user: User):

    @staticmethod
    def create_client(client_data: Dict, db: Session, current_user: Optional[User] = None) -> Dict:
        try:
            # ---------------- EXTRACT NESTED DATA ----------------
            providers = client_data.pop("providers", []) or []
            locations = client_data.pop("locations", []) or []
            primary_temp_id = client_data.pop("primary_temp_id", None)

            # ---------------- STATUS ----------------
            active_status = (
                db.query(Status)
                .filter(Status.code == "ACTIVE")
                .first()
            )

            # ---------------- CREATED BY / ORG LOGIC ----------------
            created_by_val = None
            organisation_id_val = None

            if current_user:
                if isinstance(current_user, Organisation):
                    organisation_id_val = str(current_user.id)

                elif isinstance(current_user, User):
                    if not current_user.is_superuser:
                        created_by_val = str(current_user.id)
                        organisation_id_val = (
                            str(current_user.organisation_id)
                            if current_user.organisation_id
                            else None
                        )

            # ---------------- CLEAN CLIENT PAYLOAD ----------------
            client_payload = client_data.copy()
            client_payload.pop("status_id", None)
            client_payload.pop("created_by", None)
            client_payload.pop("organisation_id", None)
            client_payload.pop("user_id", None)

            # ---------------- CREATE CLIENT ----------------
            client = Client(
                status_id=active_status.id if active_status else None,
                created_by=created_by_val,
                organisation_id=organisation_id_val,
                **client_payload
            )

            db.add(client)
            db.flush()  # client.id available

            # ---------------- TEMP → REAL LOCATION MAP ----------------
            temp_to_real: Dict[str, int] = {}

            # ---------------- PRIMARY LOCATION ----------------
            # primary_location = ClientLocation(
            #     client_id=client.id,
            #     address_line_1=client.address_line_1,
            #     address_line_2=client.address_line_2,
            #     city=client.city,
            #     state_code=client.state_code,
            #     state_name=client.state_name,
            #     zip_code=client.zip_code,
            #     country=client.country,
            #     is_primary=True,
            #     created_by=created_by_val,
            # )

            # db.add(primary_location)
            # db.flush()

            # if primary_temp_id:
            #     temp_to_real[primary_temp_id] = primary_location.id

            # ---------------- EXTRA LOCATIONS ----------------
            for loc in locations:
                if not loc.get("address_line_1"):
                    continue

                temp_id = loc.get("temp_id")
                if not temp_id:
                    raise ValueError("Location missing temp_id")

                new_loc = ClientLocation(
                    client_id=client.id,
                    address_line_1=loc.get("address_line_1"),
                    address_line_2=loc.get("address_line_2"),
                    city=loc.get("city"),
                    state_code=loc.get("state_code"),
                    state_name=loc.get("state_name"),
                    zip_code=loc.get("zip_code"),
                    country=loc.get("country"),
                    is_primary=loc.get("is_primary"),
                    created_by=created_by_val,
                )

                db.add(new_loc)
                db.flush()
                temp_to_real[temp_id] = new_loc.id

            # ---------------- PROVIDERS ----------------
            for provider in providers:
                temp_id = provider.get("location_temp_id")
                if not temp_id:
                    raise ValueError("Provider must choose organization location")

                real_location_id = temp_to_real.get(temp_id)
                if not real_location_id:
                    raise ValueError(f"Invalid provider location mapping: {temp_id}")

                provider_data = {
                    k: v for k, v in provider.items()
                    if k != "location_temp_id"
                }

                db.add(
                    Provider(
                        client_id=client.id,
                        location_id=real_location_id,
                        created_by=created_by_val,
                        **provider_data
                    )
                )

            # ---------------- COMMIT ----------------
            db.commit()
            db.refresh(client)

            return ClientService._format_client(client, db)

        except Exception:
            db.rollback()
            raise

      

    # @staticmethod
    # def create_client(client_data: Dict, db: Session, current_user: User) -> Dict:
    #     print("INCOMING CLIENT DATA:", client_data)

    #     client_type = client_data.get("type")
    #     providers = client_data.pop("providers", None)
    #     locations = client_data.pop("locations", None)
    #     print("PROVIDERS:", providers)
    #     print("LOCATIONS:", locations)
    #     # -------- NPI-1 (Individual) --------
    #     if client_type == "NPI1":
    #         client = Client(
    #             first_name=client_data.get("first_name"),
    #             middle_name=client_data.get("middle_name"),
    #             last_name=client_data.get("last_name"),
    #             npi=client_data.get("npi"),
    #             type="NPI1",

    #             address_line_1=client_data.get("address_line_1"),
    #             address_line_2=client_data.get("address_line_2"),
    #             city=client_data.get("city"),
    #             state_code=client_data.get("state_code"),
    #             state_name=client_data.get("state_name"),
    #             country=client_data.get("country"),
    #             zip_code=client_data.get("zip_code"),

    #             description=client_data.get("description"),
    #         )
    #         db.add(client)
    #         db.commit()
    #         db.refresh(client)

    #         # ❌ NO USER LINKING HERE
    #         return ClientService._format_client(client, db)

    #     # -------- NPI-2 (Organization) --------
    #     if client_type == "NPI2":

    #         zip_code = client_data.get("zip_code")

    #         print("BACKEND ORG ZIP:", zip_code)
    #         print("BACKEND PROVIDERS:", providers)

    #         if not zip_code:
    #             raise ValueError("ORG ZIP missing")

    #         client = Client(
    #             business_name=client_data["business_name"],
    #             npi=client_data.get("npi"),
    #             type="NPI2",
    #             address_line_1=client_data.get("address_line_1"),
    #             address_line_2=client_data.get("address_line_2"),
    #             city=client_data.get("city"),
    #             state_code=client_data.get("state_code"),
    #             state_name=client_data.get("state_name"),
    #             country=client_data.get("country"),
    #             zip_code=zip_code,
    #         )
    #         client.created_by = current_user.id
    #         client.status_id = db.query(Status.id).filter(Status.code == "ACTIVE").scalar()
    #         db.add(client)
    #         db.flush()

    #         db.add(ClientLocation(
    #             client_id=client.id,
    #             address_line_1=client.address_line_1,
    #             address_line_2=client.address_line_2,
    #             city=client.city,
    #             state_code=client.state_code,
    #             state_name=client.state_name,
    #             country=client.country,
    #             zip_code=zip_code,
    #             is_primary=True,
    #         ))
    #         if locations:
    #             ClientService._create_secondary_locations(
    #                 client_id=client.id,
    #                 locations=locations,
    #                 db=db
    #             )
    #         if providers:
    #             print("RAW PROVIDERS FROM FRONTEND:", providers)

    #             for p in providers:
    #                 if not p.get("zip_code") or p.get("zip_code") == "":
    #                     raise ValueError(f"Provider ZIP missing → {p}")
    #                 location_id = p.get("location_id")
    #                 provider_data = {k: v for k, v in p.items() if k != "location_id"}
    #                 db.add(Provider(
    #                     client_id=client.id,
    #                     location_id=location_id,
    #                     **provider_data
    #                 ))

    #         try:
    #             db.commit()
    #             print("COMMIT SUCCESS")
    #         except Exception as e:
    #             print("COMMIT FAILED:", e)
    #             db.rollback()
    #             raise

    #         db.refresh(client)
    #         return ClientService._format_client(client, db)



    @staticmethod
    def _create_secondary_locations(
        client_id: str,
        locations: List[Dict],
        db: Session
    ):
        if not locations:
            return

        required = ["address_line_1", "city", "state_code", "zip_code"]

        for loc in locations:
            if loc.get("is_primary"):
                raise ValueError("Primary location must be defined on client")

            for f in required:
                if not loc.get(f):
                    raise ValueError("Invalid secondary location")
            loc = {k: v for k, v in loc.items() if k != "is_primary"}

            db.add(ClientLocation(
                client_id=client_id,
                is_primary=False,
                **loc
            ))


    @staticmethod
    def _create_providers(
        client_id: str,
        providers: Optional[List[Dict]],
        db: Session
    ):
        if not providers:
            return  # ✅ nothing to do

        for p in providers:
            db.add(Provider(
                client_id=client_id,
                **p
            ))


    @staticmethod
    def _link_user(client: Client, user_id: str, db: Session):
        # Ownership only — NO user_client
        UserService.link_client_owner(db, user_id, client.id)

    @staticmethod
    def update_client(client_id: str, client_data: Dict, db: Session) -> Optional[Dict]:

        client = db.query(Client).filter(
            Client.id == client_id,
            Client.deleted_at.is_(None)
        ).first()

        if not client:
            return None

        providers = client_data.pop("providers", None)
        locations = client_data.pop("locations", None)
        primary_temp_id = client_data.pop("primary_temp_id", None)

        try:
            # -------------------------------------------------
            # UPDATE CLIENT FIELDS
            # -------------------------------------------------
            for key, value in client_data.items():
                setattr(client, key, value)

            # -------------------------------------------------
            # LOCATIONS
            # -------------------------------------------------
            primary_loc = db.query(ClientLocation).filter(
                ClientLocation.client_id == client.id,
                ClientLocation.is_primary.is_(True)
            ).first()

            if not primary_loc:
                raise RuntimeError("Primary location missing")

            temp_to_real: Dict[str, str] = {}
            if primary_temp_id:
                temp_to_real[primary_temp_id] = primary_loc.id

            # sync primary address with client
            for f in [
                "address_line_1", "address_line_2", "city",
                "state_code", "state_name", "country", "zip_code"
            ]:
                setattr(primary_loc, f, getattr(client, f))

            if locations is not None:
                db.query(ClientLocation).filter(
                    ClientLocation.client_id == client.id,
                    ClientLocation.is_primary.is_(False)
                ).delete()

                for loc in locations:
                    if not loc.get("address_line_1"):
                        continue
                    if loc.get("temp_id") == primary_temp_id:
                        continue

                    new_loc = ClientLocation(
                        client_id=client.id,
                        is_primary=False,
                        **loc
                    )
                    db.add(new_loc)
                    db.flush()
                    temp_to_real[loc["temp_id"]] = new_loc.id

            # -------------------------------------------------
            # PROVIDER MAPPING (REPLACE)
            # -------------------------------------------------
            if providers is not None:
                db.query(ProviderClientMap).filter(
                    ProviderClientMap.client_id == client.id
                ).delete()

                for p in providers:
                    temp_id = p.get("location_temp_id")

                    if temp_id not in temp_to_real:
                        raise ValueError(f"Invalid provider location mapping: {temp_id}")

                    location_id = temp_to_real[temp_id]

                    provider = db.query(Provider).filter(
                        Provider.npi == p["npi"]
                    ).first()

                    if not provider:
                        provider = Provider(
                            npi=p["npi"],
                            first_name=p.get("first_name"),
                            middle_name=p.get("middle_name"),
                            last_name=p.get("last_name"),
                            address_line_1=p.get("address_line_1"),
                            address_line_2=p.get("address_line_2"),
                            city=p.get("city"),
                            state_code=p.get("state_code"),
                            state_name=p.get("state_name"),
                            country=p.get("country"),
                            zip_code=p.get("zip_code"),
                        )
                        db.add(provider)
                        db.flush()

                    db.add(
                        ProviderClientMap(
                            provider_id=provider.id,
                            client_id=client.id,
                            location_id=location_id
                        )
                    )

            db.commit()
            db.refresh(client)
            return ClientService._format_client(client, db)

        except Exception:
            db.rollback()
            raise


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
            
            # 1. Direct link on Client (Owner)
            if client.created_by:
                linked_user = db.query(User).filter(User.id == client.created_by).first()
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
    def assign_clients_to_user(
        user_id: str,
        client_ids: List[str],
        assigned_by: str,
        db: Session
    ):

        stmt = insert(UserClient).values([
            {
                "id": str(uuid.uuid4()),
                "user_id": user_id,
                "client_id": cid,
                "assigned_by": assigned_by
            }
            for cid in client_ids
        ]).on_conflict_do_nothing(
            index_elements=["user_id", "client_id"]
        )

        db.execute(stmt)
        db.commit()

    @staticmethod
    def map_users_to_client(
        client_id: str,
        user_ids: List[str],
        assigned_by: str,
        db: Session
    ):
        # Insert ignoring duplicates
        stmt = insert(UserClient).values([
            {
                "id": str(uuid.uuid4()),
                "user_id": uid,
                "client_id": client_id,
                "assigned_by": assigned_by
            }
            for uid in user_ids
        ]).on_conflict_do_nothing(
            index_elements=["user_id", "client_id"]
        )
        
        db.execute(stmt)
        db.commit()

    @staticmethod
    def unassign_users_from_client(
        client_id: str,
        user_ids: List[str],
        db: Session
    ):
        if not user_ids:
            return
            
        db.query(UserClient).filter(
            UserClient.client_id == client_id,
            UserClient.user_id.in_(user_ids)
        ).delete(synchronize_session=False)
        db.commit()

    @staticmethod
    def get_user_clients(user_id: str, db: Session) -> List[Dict]:
        user_clients = db.query(Client).join(UserClient, Client.id == UserClient.client_id).filter(
            UserClient.user_id == user_id,
            Client.deleted_at.is_(None)
        ).order_by(Client.created_at.desc()).all()
        return [ClientService._format_client(c, db) for c in user_clients]
    
    @staticmethod
    def check_npi_exists(npi: str, exclude_client_id: Optional[str], db: Session) -> bool:
        q1 = db.query(Client).filter(
            Client.npi == npi,
            Client.deleted_at.is_(None)
        )
        if exclude_client_id:
            q1 = q1.filter(Client.id != exclude_client_id)

        if q1.first():
            return True

        return db.query(
            db.query(Provider).filter(Provider.npi == npi).exists()
        ).scalar()

    @staticmethod
    def get_client_by_id(client_id: str, db: Session) -> Optional[Dict]:
        client = (
            db.query(Client)
            .filter(Client.id == client_id, Client.deleted_at.is_(None))
            .first()
        )
        if not client:
            return None

        return ClientService._format_client(client, db, detailed=True)

    @staticmethod
    def _format_client(client: Client, db: Session = None, detailed: bool = True) -> Dict:
        status_code = None
        if db and client.status_id:
            status = db.query(Status).filter(Status.id == client.status_id).first()
            status_code = status.code if status else None

        providers: List[Dict] = []
        locations: List[Dict] = []

        if db and detailed and client.type == "NPI2":
            provider_rows = (
                db.query(Provider)
                .filter(Provider.client_id == client.id)
                .all()
            )

            providers = [
                {
                    "id": p.id,
                    "first_name": p.first_name,
                    "middle_name": p.middle_name,
                    "last_name": p.last_name,
                    "npi": p.npi,
                    "address_line_1": p.address_line_1,
                    "address_line_2": p.address_line_2,
                    "city": p.city,
                    "state_code": p.state_code,
                    "state_name": p.state_name,
                    "country": p.country,
                    "zip_code": p.zip_code,
                    "location_id": p.location_id,
                    "created_at": p.created_at,
                }
                for p in provider_rows
            ]
            location_rows = (
                db.query(ClientLocation)
                .filter(ClientLocation.client_id == client.id)
                .order_by(ClientLocation.is_primary.desc())
                .all()
            )

            locations = [
                {
                    "id": loc.id,
                    "address_line_1": loc.address_line_1,
                    "address_line_2": loc.address_line_2,
                    "city": loc.city,
                    "state_code": loc.state_code,
                    "state_name": loc.state_name,
                    "country": loc.country,
                    "zip_code": loc.zip_code,
                    "is_primary": loc.is_primary,
                }
                for loc in location_rows
            ]
        has_owner = client.created_by is not None
        has_any_user = (
            db.query(UserClient)
            .filter(UserClient.client_id == client.id)
            .count() > 0
        ) if db else False

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
            "status_code": status_code,
            "statusCode": status_code,
            "description": client.description,

            # NPA1 / base address fields
            "address_line_1": client.address_line_1,
            "address_line_2": client.address_line_2,
            "city": client.city,
            "state_code": client.state_code,
            "state_name": client.state_name,
            "country": client.country,
            "zip_code": client.zip_code,

            # NPA2 only
            "providers": providers,
            "locations": locations,

            "user_count": 0,
            "assigned_users": [],
            "created_at": client.created_at,
            "updated_at": client.updated_at,
            "has_owner": has_owner,
            "has_any_user": has_owner or has_any_user,
        }
