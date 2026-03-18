from fastapi import HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, or_, select
from typing import Optional, List, Dict, Tuple
import uuid
from datetime import datetime
from sqlalchemy.dialects.postgresql import insert

from app.models.client import Client
from app.models.client_location import ClientLocation
from app.models.organisation import Organisation
from app.models.provider import Provider
from app.models.provider_client_mapping import ProviderClientMapping
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
        org_id = getattr(current_user, "context_organisation_id", None) or getattr(current_user, "organisation_id", None)
        is_super = getattr(current_user, "context_is_superadmin", getattr(current_user, "is_superuser", False))

        if not is_super and not org_id:
            raise HTTPException(403, "No organisation selected")

        active_status = db.query(Status.id).filter(
            Status.code == "ACTIVE"
        ).scalar()

        query = db.query(Client).filter(
            Client.status_id == active_status,
            Client.deleted_at.is_(None)
        )
        
        if org_id:
            query = query.filter(Client.organisation_id == org_id)

        clients = query.order_by(Client.business_name).all()

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
    def get_client_stats(db: Session, current_user: User):

        org_id = getattr(current_user, "context_organisation_id", None) or current_user.organisation_id
        is_super = getattr(current_user, "context_is_superadmin", current_user.is_superuser)

        base_query = db.query(Client).filter(
            Client.deleted_at.is_(None)
        )

        if not is_super:
            if not org_id:
                raise HTTPException(403, "No organisation selected")
            base_query = base_query.filter(Client.organisation_id == org_id)
        elif org_id:
            base_query = base_query.filter(Client.organisation_id == org_id)

        total_clients = base_query.count()

        active_status = db.query(Status).filter(Status.code == "ACTIVE").first()
        inactive_status = db.query(Status).filter(Status.code == "INACTIVE").first()

        active_clients = (
            base_query.filter(Client.status_id == active_status.id).count()
            if active_status else 0
        )

        inactive_clients = (
            base_query.filter(Client.status_id == inactive_status.id).count()
            if inactive_status else 0
        )

        return {
            "total_clients": total_clients,
            "active_clients": active_clients,
            "inactive_clients": inactive_clients
        }


    @staticmethod
    def get_clients(
        page: int, 
        page_size: int, 
        search: Optional[str], 
        status_id: Optional[str], 
        db: Session, 
        current_user: Optional[User] = None, 
        organisation_ids: Optional[str] = None,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None
    ) -> Tuple[List[Dict], int]:
        skip = (page - 1) * page_size
        
        from app.models.provider_client_mapping import ProviderClientMapping
        
        # Subquery for provider count
        provider_count = (
            db.query(func.count(ProviderClientMapping.id))
            .filter(ProviderClientMapping.client_id == Client.id)
            .correlate(Client)
            .as_scalar()
        )
        
        query = db.query(Client, provider_count).filter(Client.deleted_at.is_(None))
        
        org_id = getattr(current_user, "context_organisation_id", None) or current_user.organisation_id
        is_super = getattr(current_user, "context_is_superadmin", current_user.is_superuser)

        if not is_super:
            if not org_id:
                raise HTTPException(403, "No organisation selected")
            query = query.filter(Client.organisation_id == org_id)
        elif org_id:
            query = query.filter(Client.organisation_id == org_id)
        
        if status_id:
            status_codes = status_id.split(',')
            query = query.join(Client.status_relation).filter(Status.code.in_(status_codes))
            
        if from_date:
            query = query.filter(Client.created_at >= from_date)
        if to_date:
            query = query.filter(Client.created_at <= to_date)
        
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
        results = query.order_by(Client.created_at.desc()).offset(skip).limit(page_size).all()
        
        return [
            ClientService._format_client(client, db, detailed=False, provider_count=count) 
            for client, count in results
        ], total

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
                org_id = getattr(current_user, "context_organisation_id", None) or getattr(current_user, "organisation_id", None)
                is_super = getattr(current_user, "context_is_superadmin", getattr(current_user, "is_superuser", False))

                if not is_super and not org_id:
                    raise HTTPException(403, "No organisation selected")

                organisation_id_val = org_id
                created_by_val = str(current_user.id) if hasattr(current_user, "id") else None

            # ---------------- CLEAN CLIENT PAYLOAD ----------------
            client_payload = client_data.copy()
            client_payload.pop("status_id", None)
            client_payload.pop("created_by", None)
            client_payload.pop("organisation_id", None)
            client_payload.pop("user_id", None)

            # ---------------- NORMALIZE CLIENT TYPE ----------------
            raw_type = client_payload.get("type")

            if raw_type:
                normalized = raw_type.lower().replace("-", "").replace(" ", "")

                individual_keywords = {
                    "individual",
                    "npi1",
                    "npi-1",
                    "individual npi1",
                    "individual npi-1"
                }

                if any(keyword in normalized for keyword in individual_keywords):
                    client_payload["type"] = "Individual"

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
                    if k not in ["location_temp_id", "location_id", "created_by"]
                }
                
                # Check directly in payload for npi
                npi_val = provider_data.get("npi")
                if not npi_val:
                     raise ValueError("Provider NPI is required")

                # Check if provider exists
                existing_provider = db.query(Provider).filter(Provider.npi == npi_val).first()

                if existing_provider:
                     # Link existing provider
                     mapping = ProviderClientMapping(
                         provider_id=existing_provider.id,
                         client_id=client.id,
                         location_id=real_location_id,
                         created_by=created_by_val
                     )
                     db.add(mapping)
                else:
                    # Create new provider
                    new_prov = Provider(
                        # location_id removed from Provider
                        created_by=created_by_val,
                        **provider_data
                    )
                    db.add(new_prov)
                    db.flush() # get ID
                    
                    mapping = ProviderClientMapping(
                         provider_id=new_prov.id,
                         client_id=client.id,
                         location_id=real_location_id,
                         created_by=created_by_val
                     )
                    db.add(mapping)

            # ---------------- COMMIT ----------------
            db.commit()
            db.refresh(client)

            return ClientService._format_client(client, db)

        except Exception:
            db.rollback()
            raise

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
    def update_client(client_id: str, client_data: Dict, db: Session, current_user: User) -> Optional[Dict]:

        org_id = getattr(current_user, "context_organisation_id", None) or getattr(current_user, "organisation_id", None)
        is_super = getattr(current_user, "context_is_superadmin", getattr(current_user, "is_superuser", False))

        if not is_super and not org_id:
            raise HTTPException(403, "No organisation selected")

        query = db.query(Client).filter(
            Client.id == client_id,
            Client.deleted_at.is_(None)
        )

        if org_id:
            query = query.filter(Client.organisation_id == org_id)

        client = query.first()

        if not client:
            return None

        providers_data = client_data.pop("providers", None)
        locations_data = client_data.pop("locations", None)

        try:

            # -------------------------------------------------
            # UPDATE BASIC CLIENT FIELDS (NON ADDRESS)
            # -------------------------------------------------
            for key, value in client_data.items():
                if hasattr(client, key):
                    setattr(client, key, value)

            # -------------------------------------------------
            # PRIMARY LOCATION (SOURCE OF TRUTH)
            # -------------------------------------------------
            primary_loc = db.query(ClientLocation).filter(
                ClientLocation.client_id == client.id,
                ClientLocation.is_primary.is_(True)
            ).first()

            if not primary_loc:
                primary_loc = ClientLocation(
                    client_id=client.id,
                    is_primary=True,
                    created_by=client.created_by
                )
                db.add(primary_loc)
                db.flush()

            if locations_data is not None:
                for loc_item in locations_data:
                    if loc_item.get("is_primary"):

                        for field in [
                            "address_line_1",
                            "address_line_2",
                            "city",
                            "state_code",
                            "state_name",
                            "country",
                            "zip_code"
                        ]:
                            if field in loc_item:
                                setattr(primary_loc, field, loc_item.get(field))

                        break

            # Sync CLIENT table from PRIMARY location
            client.address_line_1 = primary_loc.address_line_1
            client.address_line_2 = primary_loc.address_line_2
            client.city = primary_loc.city
            client.state_code = primary_loc.state_code
            client.state_name = primary_loc.state_name
            client.country = primary_loc.country
            client.zip_code = primary_loc.zip_code

            # -------------------------------------------------
            # SECONDARY LOCATIONS
            # -------------------------------------------------
            if locations_data is not None:

                existing_secondary = db.query(ClientLocation).filter(
                    ClientLocation.client_id == client.id,
                    ClientLocation.is_primary.is_(False)
                ).all()

                existing_map = {str(loc.id): loc for loc in existing_secondary}
                payload_ids = set()

                for loc_item in locations_data:

                    if loc_item.get("is_primary"):
                        continue

                    loc_id = loc_item.get("id")

                    # UPDATE EXISTING
                    if loc_id and str(loc_id) in existing_map:
                        loc_obj = existing_map[str(loc_id)]

                        for k, v in loc_item.items():
                            if k in ["id", "is_primary"]:
                                continue
                            if hasattr(loc_obj, k):
                                setattr(loc_obj, k, v)

                        payload_ids.add(str(loc_id))
                        continue

                    # CREATE NEW (ONLY if NO ID)
                    if not loc_id:
                        if not loc_item.get("address_line_1"):
                            continue

                        new_loc = ClientLocation(
                            client_id=client.id,
                            is_primary=False,
                            address_line_1=loc_item.get("address_line_1"),
                            address_line_2=loc_item.get("address_line_2"),
                            city=loc_item.get("city"),
                            state_code=loc_item.get("state_code"),
                            state_name=loc_item.get("state_name"),
                            country=loc_item.get("country"),
                            zip_code=loc_item.get("zip_code"),
                            created_by=client.created_by
                        )
                        db.add(new_loc)

                # DELETE removed secondary locations
                for eid, eloc in existing_map.items():
                    if eid not in payload_ids:
                        db.delete(eloc)

            # -------------------------------------------------
            # PROVIDERS
            # -------------------------------------------------
            if providers_data is not None:

                existing_mappings = db.query(ProviderClientMapping).filter(
                    ProviderClientMapping.client_id == client.id
                ).all()

                mapping_map = {str(m.provider_id): m for m in existing_mappings}
                payload_provider_ids = set()

                for p_item in providers_data:

                    location_id = p_item.get("location_id")

                    if not location_id:
                        location_id = primary_loc.id

                    npi_val = p_item.get("npi")
                    if not npi_val:
                        continue

                    provider_obj = db.query(Provider).filter(
                        Provider.npi == npi_val
                    ).first()

                    # UPDATE EXISTING PROVIDER
                    if provider_obj:

                        provider_obj.first_name = p_item.get("first_name", provider_obj.first_name)
                        provider_obj.middle_name = p_item.get("middle_name", provider_obj.middle_name)
                        provider_obj.last_name = p_item.get("last_name", provider_obj.last_name)
                        provider_obj.address_line_1 = p_item.get("address_line_1", provider_obj.address_line_1)
                        provider_obj.address_line_2 = p_item.get("address_line_2", provider_obj.address_line_2)
                        provider_obj.city = p_item.get("city", provider_obj.city)
                        provider_obj.state_code = p_item.get("state_code", provider_obj.state_code)
                        provider_obj.state_name = p_item.get("state_name", provider_obj.state_name)
                        provider_obj.country = p_item.get("country", provider_obj.country)
                        provider_obj.zip_code = p_item.get("zip_code", provider_obj.zip_code)
                        provider_obj.specialty = p_item.get("specialty", provider_obj.specialty)
                        provider_obj.specialty_code = p_item.get("specialty_code", provider_obj.specialty_code)

                        if str(provider_obj.id) in mapping_map:
                            mapping_map[str(provider_obj.id)].location_id = location_id
                        else:
                            db.add(ProviderClientMapping(
                                provider_id=provider_obj.id,
                                client_id=client.id,
                                location_id=location_id,
                                created_by=client.created_by
                            ))

                        payload_provider_ids.add(str(provider_obj.id))

                    # CREATE NEW PROVIDER
                    else:
                        new_prov = Provider(
                            first_name=p_item.get("first_name"),
                            middle_name=p_item.get("middle_name"),
                            last_name=p_item.get("last_name"),
                            npi=npi_val,
                            address_line_1=p_item.get("address_line_1"),
                            address_line_2=p_item.get("address_line_2"),
                            city=p_item.get("city"),
                            state_code=p_item.get("state_code"),
                            state_name=p_item.get("state_name"),
                            country=p_item.get("country"),
                            zip_code=p_item.get("zip_code"),
                            specialty=p_item.get("specialty"),
                            specialty_code=p_item.get("specialty_code"),
                            created_by=client.created_by
                        )
                        db.add(new_prov)
                        db.flush()

                        db.add(ProviderClientMapping(
                            provider_id=new_prov.id,
                            client_id=client.id,
                            location_id=location_id,
                            created_by=client.created_by
                        ))

                        payload_provider_ids.add(str(new_prov.id))

                # DELETE removed mappings
                for m in existing_mappings:
                    if str(m.provider_id) not in payload_provider_ids:
                        db.delete(m)

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
           
            if client.created_by:
                linked_user = db.query(User).filter(User.id == client.created_by).first()
                if linked_user and not linked_user.is_superuser:
                    linked_user.status_id = inactive_status.id

            linked_users_via_junction = db.query(User).join(UserClient, User.id == UserClient.user_id).filter(
                UserClient.client_id == client.id
            ).all()

            for user in linked_users_via_junction:
                if not user.is_superuser:
                    user.status_id = inactive_status.id

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
        db: Session,
        current_user: User
    ):
        
        # Check Role
        is_org_role = False
        if hasattr(current_user, 'roles'):
            role_names = [r.name for r in current_user.roles]
            if "ORGANISATION_ADMIN" in role_names:
                is_org_role = True

        # Determine assignment fields
        final_assigned_by = None
        final_organisation_id = None

        if is_org_role:
            
             final_organisation_id = assigned_by
        else:
             final_assigned_by = assigned_by

        # Insert ignoring duplicates
        stmt = insert(UserClient).values([
            {
                "id": str(uuid.uuid4()),
                "user_id": uid,
                "client_id": client_id,
                "assigned_by": final_assigned_by,
                "organisation_id": final_organisation_id
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
    def get_client_by_id(client_id: str, db: Session, current_user):
        org_id = getattr(current_user, "context_organisation_id", None)
        if not org_id:
            raise HTTPException(403, "No organisation selected")

        client = (
            db.query(Client)
            .filter(
                Client.id == client_id,
                Client.organisation_id == org_id,
                Client.deleted_at.is_(None)
            )
            .first()
        )
        if not client:
            return None

        return ClientService._format_client(client, db, detailed=True)

    @staticmethod
    def _format_client(client: Client, db: Session = None, detailed: bool = True, provider_count: int = 0) -> Dict:
        status_code = None
        if db and client.status_id:
            status = db.query(Status).filter(Status.id == client.status_id).first()
            status_code = status.code if status else None

         # Fetch Organisation Name
        organisation_name = None
        org_id = getattr(client, 'organisation_id', None)
        if org_id:
             org = db.query(Organisation).filter(Organisation.id == org_id).first()
             if org:
                 # Organisation doesn't have business_name, using first/last or username
                 organisation_name = f"{org.name}".strip()
                 if not organisation_name:
                     organisation_name = org.username

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

        providers: List[Dict] = []
        locations: List[Dict] = []

        if db and detailed and client.type == "NPI2":
            provider_rows = (
                db.query(Provider, ProviderClientMapping)
                .join(ProviderClientMapping, Provider.id == ProviderClientMapping.provider_id)
                .filter(ProviderClientMapping.client_id == client.id)
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
                    "location_id": str(m.location_id) if m and m.location_id else None,
                    "specialty": p.specialty,
                    "specialty_code": p.specialty_code,
                    "ptan_id": p.ptan_id,
                    "created_at": p.created_at,
                }
                for p, m in provider_rows
            ]
            location_rows = (
                db.query(ClientLocation)
                .filter(ClientLocation.client_id == client.id)
                .order_by(ClientLocation.is_primary.desc())
                .all()
            )

            locations = [
                {
                    "id": str(loc.id),
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
            "id": client.id,
            "business_name": client.business_name,
            "first_name": client.first_name,
            "middle_name": client.middle_name,
            "last_name": client.last_name,
            "npi": client.npi,
            "is_user": client.is_user,
            "provider_count": provider_count,
            "type": client.type,
            "status_id": client.status_id,
            "status_code": status_code,
            "description": client.description,
            "specialty": client.specialty,
            "specialty_code": client.specialty_code,
            "created_at": client.created_at,
            "updated_at": client.updated_at,
            "organisation_name": organisation_name,
            
            # --- ADDRESS FIELDS ---
            "address_line_1": client.address_line_1,
            "address_line_2": client.address_line_2,
            "city": client.city,
            "state_code": client.state_code,
            "state_name": client.state_name,
            "zip_code": client.zip_code,
            "country": client.country,
            
            # --- NESTED DATA --- 
            "providers": providers,
            "locations": locations,

            # --- USER COUNTS (Already existed) ---
            # "user_count": client.user_count if hasattr(client, 'user_count') else 0,
             "user_count": len(assigned_users),
            "assigned_users": client.assigned_users if hasattr(client, 'assigned_users') else [],
            "has_owner": has_owner,
            "has_any_user": has_owner or has_any_user,
        }

    @staticmethod
    def get_providers_by_client(
        client_id: str,
        page: int,
        page_size: int,
        search: Optional[str],
        db: Session
    ) -> Tuple[List[Dict], int]:
        skip = (page - 1) * page_size
        
        query = (
            db.query(Provider, ProviderClientMapping)
            .join(ProviderClientMapping, Provider.id == ProviderClientMapping.provider_id)
            .filter(ProviderClientMapping.client_id == client_id)
        )
        
        if search:
            search_term = f"%{search}%"
            query = query.filter(
                or_(
                    Provider.first_name.ilike(search_term),
                    Provider.middle_name.ilike(search_term),
                    Provider.last_name.ilike(search_term),
                    Provider.npi.ilike(search_term)
                )
            )
            
        total = query.count()
        providers = query.order_by(Provider.created_at.desc()).offset(skip).limit(page_size).all()
        
        formatted_providers = [
            {
                "id": str(p.id),
                "name": f"{p.first_name} {p.middle_name or ''} {p.last_name}".strip().replace("  ", " "),
                "first_name": p.first_name,
                "middle_name": p.middle_name,
                "last_name": p.last_name,
                "npi": p.npi,
                "type": "Individual", # Default as per requirement
                "address_line_1": p.address_line_1,
                "address_line_2": p.address_line_2,
                "city": p.city,
                "state_code": p.state_code,
                "state_name": p.state_name,
                "country": p.country,
                "zip_code": p.zip_code,
                "location_id": str(m.location_id) if m and m.location_id else None,
                "created_at": p.created_at
            }
            for p, m in providers
        ]
        
        return formatted_providers, total

    @staticmethod
    def get_all_clients(db: Session, current_user: User) -> List[Dict]:
        """
        Fetch clients based on role for SOP creation.
        - SUPER_ADMIN: All active clients
        - ORGANISATION_ADMIN: Clients in the user's organisation
        - Other: Clients created by the user
        """
        active_status = db.query(Status).filter(Status.code == "ACTIVE").first()
        status_id = active_status.id if active_status else None

        # Subquery for provider count
        provider_count_subquery = (
            db.query(func.count(ProviderClientMapping.id))
            .filter(ProviderClientMapping.client_id == Client.id)
            .correlate(Client)
            .as_scalar()
        )

        query = db.query(Client, provider_count_subquery.label("provider_count")).filter(Client.deleted_at.is_(None))
        
        if status_id:
            query = query.filter(Client.status_id == status_id)

        # Get role names
        role_names = [r.name for r in current_user.roles]

        # 1. SUPER_ADMIN
        # if current_user.is_superuser or "SUPER_ADMIN" in role_names:
        #     # Fetch all active clients
        #     pass
        
        # # 2. ORG_ADMIN
        # elif "ORGANISATION_ADMIN" in role_names:
        #     if current_user.id:
        #         query = query.filter(Client.organisation_id == str(current_user.id))
        #     else:
        #         return []
        
        # # 3. Other Roles
        # else:
        #     query = query.filter(
        #         or_(
        #             Client.created_by == str(current_user.id),
        #             Client.id.in_(
        #                 # Subquery for assigned clients
        #                 db.query(UserClient.client_id).filter(UserClient.user_id == str(current_user.id))
        #             )
        #         )
        #     )
        org_id = getattr(current_user, "context_organisation_id", None)
        if not org_id:
            raise HTTPException(403, "No organisation selected")

        query = query.filter(Client.organisation_id == org_id)
        results = query.order_by(Client.business_name).all()
        
        # Map to simple response
        return [
            {
                "id": str(c.id),
                "name": c.business_name or f"{c.first_name} {c.last_name}",
                "npi": c.npi,
                "type": c.type,
                "provider_count": count
            }
            for c, count in results
        ]
