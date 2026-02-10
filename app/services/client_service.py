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
    def get_client_stats(db: Session, current_user) -> Dict:

        base_query = db.query(Client).filter(Client.deleted_at.is_(None))

        # 🔥 SUPERADMIN
        if isinstance(current_user, User) and current_user.is_superuser:
            pass

        # 🔥 CLIENT USER
        elif isinstance(current_user, User) and current_user.is_client:
            base_query = base_query.filter(
                Client.created_by == str(current_user.id)
            )

        # 🔥 ORG LOGIN
        elif isinstance(current_user, Organisation):
            base_query = base_query.filter(
                Client.organisation_id == str(current_user.id)
            )

        # 🔥 ORG USER
        elif isinstance(current_user, User):
            base_query = base_query.filter(
                Client.organisation_id == str(current_user.organisation_id)
            )

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
    def get_clients(page: int, page_size: int, search: Optional[str], status_id: Optional[str], db: Session, current_user: Optional[User] = None) -> Tuple[List[Dict], int]:
        skip = (page - 1) * page_size
        
        stmt = db.query(Client).filter(Client.deleted_at.is_(None))
        
        # Subquery for provider count
        provider_count = (
            db.query(func.count(ProviderClientMapping.id))
            .filter(ProviderClientMapping.client_id == Client.id)
            .correlate(Client)
            .as_scalar()
        )
        
        query = db.query(Client, provider_count).filter(Client.deleted_at.is_(None))
        
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
        results = query.order_by(Client.created_at.desc()).offset(skip).limit(page_size).all()
        
        return [
            ClientService._format_client(client, db, detailed=False, provider_count=count) 
            for client, count in results
        ], total

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

        # Extract nested data
        providers_data = client_data.pop("providers", None)
        locations_data = client_data.pop("locations", None)
        primary_temp_id = client_data.pop("primary_temp_id", "primary") # Use "primary" as fallback key if none provided

        try:
            # -------------------------------------------------
            # 1. UPDATE CLIENT BASIC FIELDS
            # -------------------------------------------------
            for key, value in client_data.items():
                if hasattr(client, key):
                    setattr(client, key, value)

            # -------------------------------------------------
            # 2. LOCATIONS HANDLING
            # -------------------------------------------------
            
            # Fetch Primary Location
            primary_loc = db.query(ClientLocation).filter(
                ClientLocation.client_id == client.id,
                ClientLocation.is_primary.is_(True)
            ).first()

            if not primary_loc:
                # Should not happen ideally, but if missing recreate?
                # For safety, let's create if missing, though schema implies it exists.
                primary_loc = ClientLocation(client_id=client.id, is_primary=True)
                db.add(primary_loc)
                db.flush()

            # Map temp_id -> real_id (UUID)
            # We start by mapping the known primary_temp_id to the real DB ID
            temp_to_real: Dict[str, str] = {}
            if primary_temp_id:
                temp_to_real[primary_temp_id] = str(primary_loc.id)

            # Sync primary location address from Client basic fields
            # (Because Client table duplicates primary address cols)
            for f in [
                "address_line_1", "address_line_2", "city",
                "state_code", "state_name", "country", "zip_code"
            ]:
                val = getattr(client, f, None)
                if val is not None:
                     setattr(primary_loc, f, val)

            # Process Secondary Locations (if provided)
            # If locations_data is None, we DO NOT touch secondary locations (PATCH behavior).
            # If locations_data is [], we DELETE all secondary locations.
            if locations_data is not None:
                
                # Get existing secondary locations
                existing_locs = db.query(ClientLocation).filter(
                    ClientLocation.client_id == client.id,
                    ClientLocation.is_primary.is_(False)
                ).all()
                existing_loc_map = {str(l.id): l for l in existing_locs}
                
                payload_loc_ids = set()

                for loc_item in locations_data:
                    # Skip primary if it accidentally got into this array
                    if loc_item.get("is_primary"): 
                        continue
                        
                    # Identify if it's an existing location (has ID) or new (no ID / temp_id)
                    loc_id = loc_item.get("id")
                    
                    if loc_id and str(loc_id) in existing_loc_map:
                        # --- UPDATE EXISTING ---
                        loc_obj = existing_loc_map[str(loc_id)]
                        for k, v in loc_item.items():
                            if k in ["id", "temp_id", "is_primary"]: continue
                            if hasattr(loc_obj, k):
                                setattr(loc_obj, k, v)
                        payload_loc_ids.add(str(loc_id))
                        
                        # Map temp_id if present
                        if loc_item.get("temp_id"):
                            temp_to_real[loc_item["temp_id"]] = str(loc_obj.id)
                            
                    elif loc_item.get("temp_id") and loc_item.get("temp_id") != primary_temp_id:
                         # --- CREATE NEW ---
                         # Ensure valid address
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
                         db.flush() # Get ID
                         
                         temp_to_real[loc_item["temp_id"]] = str(new_loc.id)
                         # Note: we don't add to payload_loc_ids because it wasn't in existing map
                    else:
                        print(f"DEBUG: Location item ignored. ID: {loc_id}, TempID: {loc_item.get('temp_id')}")
                
                # --- DELETE MISSING ---
                # Delete any existing secondary location NOT present in the payload
                # (Only if IDs were provided in payload. If payload items lacked IDs, they were treated as new)
                # Strategy: If the frontend sends existing items, it MUST send their IDs.
                for eid, eloc in existing_loc_map.items():
                    if eid not in payload_loc_ids:
                        db.delete(eloc)


            # -------------------------------------------------
            # 3. PROVIDERS HANDLING
            # -------------------------------------------------
            # -------------------------------------------------
            # 3. PROVIDERS HANDLING
            # -------------------------------------------------
            if providers_data is not None:
                # Fetch existing mappings
                existing_mappings = db.query(ProviderClientMapping).filter(
                     ProviderClientMapping.client_id == client.id
                ).all()
                existing_mapped_provider_ids = {str(m.provider_id) for m in existing_mappings}
                mapping_map = {str(m.provider_id): m for m in existing_mappings}
                
                payload_provider_ids = set()

                for p_item in providers_data:
                    # Resolve Location (same logic as before)
                    location_id = p_item.get("location_id")
                    location_temp = p_item.get("location_temp_id")
                    if location_temp:
                        location_id = temp_to_real.get(location_temp)
                        if not location_id:
                             try:
                                 uuid.UUID(location_temp)
                                 location_id = location_temp
                             except:
                                 pass 
                    
                    if not location_id:
                         location_id = primary_loc.id

                    # Resolve Provider by NPI
                    npi_val = p_item.get("npi")
                    if not npi_val:
                        pass

                    provider_obj = None
                    if npi_val:
                        provider_obj = db.query(Provider).filter(Provider.npi == npi_val).first()
                    
                    if provider_obj:
                        # PROVIDER EXISTS GLOBAL
                        # Update details
                        # provider_obj.location_id = location_id # REMOVED from Provider
                        
                        provider_obj.first_name = p_item.get("first_name", provider_obj.first_name)
                        provider_obj.middle_name = p_item.get("middle_name", provider_obj.middle_name)
                        provider_obj.last_name = p_item.get("last_name", provider_obj.last_name)
                        # npi is unique key, so if we found it by npi, we don't change npi usually.
                        
                        provider_obj.address_line_1 = p_item.get("address_line_1", provider_obj.address_line_1)
                        provider_obj.address_line_2 = p_item.get("address_line_2", provider_obj.address_line_2)
                        provider_obj.city = p_item.get("city", provider_obj.city)
                        provider_obj.state_code = p_item.get("state_code", provider_obj.state_code)
                        provider_obj.state_name = p_item.get("state_name", provider_obj.state_name)
                        provider_obj.country = p_item.get("country", provider_obj.country)
                        provider_obj.zip_code = p_item.get("zip_code", provider_obj.zip_code)

                        # Update Mapping (location_id)
                        if str(provider_obj.id) in mapping_map:
                             existing_map = mapping_map[str(provider_obj.id)]
                             existing_map.location_id = location_id
                        else:
                             # Create new mapping
                             new_map = ProviderClientMapping(
                                 provider_id=provider_obj.id,
                                 client_id=client.id,
                                 location_id=location_id,
                                 created_by=client.created_by
                             )
                             db.add(new_map)
                        
                        payload_provider_ids.add(str(provider_obj.id))

                    else:
                         # CREATE NEW PROVIDER
                         new_prov = Provider(
                             # location_id=location_id, # REMOVED
                             first_name=p_item.get("first_name"),
                             middle_name=p_item.get("middle_name"),
                             last_name=p_item.get("last_name"),
                             npi=p_item.get("npi"),
                             address_line_1=p_item.get("address_line_1"),
                             address_line_2=p_item.get("address_line_2"),
                             city=p_item.get("city"),
                             state_code=p_item.get("state_code"),
                             state_name=p_item.get("state_name"),
                             country=p_item.get("country"),
                             zip_code=p_item.get("zip_code"),
                             created_by=client.created_by
                         )
                         db.add(new_prov)
                         db.flush()
                         
                         # Create Mapping
                         new_map = ProviderClientMapping(
                                 provider_id=new_prov.id,
                                 client_id=client.id,
                                 location_id=location_id,
                                 created_by=client.created_by
                             )
                         db.add(new_map)
                         payload_provider_ids.add(str(new_prov.id))

                
                # --- REMOVE UNMAPPED ---
                # Delete mapping, NOT provider
                for existing_map in existing_mappings:
                    if str(existing_map.provider_id) not in payload_provider_ids:
                        db.delete(existing_map)

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
                    "location_id": m.location_id, # Fetch from mapping
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
            db.query(Provider)
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
                "created_at": p.created_at
            }
            for p in providers
        ]
        
        return formatted_providers, total

    @staticmethod
    def get_all_clients(db: Session, current_user: User) -> List[Dict]:
        """
        Fetch clients based on role for SOP creation.
        - SUPER_ADMIN: All active clients
        - ORGANISATION_ROLE: Clients in the user's organisation
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
        if current_user.is_superuser or "SUPER_ADMIN" in role_names:
            # Fetch all active clients
            pass
        
        # 2. ORG_ADMIN
        elif "ORGANISATION_ROLE" in role_names:
            if current_user.id:
                query = query.filter(Client.organisation_id == str(current_user.id))
            else:
                return []
        
        # 3. Other Roles
        else:
            query = query.filter(Client.created_by == str(current_user.id))

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
