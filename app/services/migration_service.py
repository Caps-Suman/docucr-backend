from sqlalchemy.orm import Session
from sqlalchemy import text
import uuid
from datetime import datetime, timezone

from app.models.module import Base, Module
from app.models.privilege import Privilege
from app.models.role import Role
from app.models.status import Status
from app.models.user import User
from app.models.user_role import UserRole
from app.models.role_module import RoleModule
from app.models.printer import Printer
from app.core.security import get_password_hash

class MigrationService:
    @staticmethod
    def initialize_printer_table(db: Session):
        """
        Initializes the printer table if it doesn't exist.
        """
        try:
            # Ensure Printer model is loaded (imported above)
            # Create schema if not exists (handled generally but good to be safe)
            db.execute(text("CREATE SCHEMA IF NOT EXISTS docucr"))
            db.commit()
            
            # Create specific table using target metadata
            # Using create_all with checking is standard
            Printer.__table__.create(db.get_bind(), checkfirst=True)
            db.commit()
            
            return {"message": "Printer table initialized successfully"}
        except Exception as e:
            db.rollback()
            raise Exception(f"Printer initialization failed: {str(e)}")

    @staticmethod
    def initialize_activity_log_table(db: Session):
        """
        Initializes the activity_log table if it doesn't exist.
        """
        try:
            # Lazy import to avoid circular dependency if any, but regular import is fine too
            from app.models.activity_log import ActivityLog
            
            db.execute(text("CREATE SCHEMA IF NOT EXISTS docucr"))
            db.commit()
            
            ActivityLog.__table__.create(db.get_bind(), checkfirst=True)
            db.commit()
            
            return {"message": "Activity Log table initialized successfully"}
        except Exception as e:
            db.rollback()
            raise Exception(f"Activity log initialization failed: {str(e)}")

    @staticmethod
    def initialize_sop_table(db: Session):
        """
        Initializes the SOP table if it doesn't exist.
        """
        try:
            from app.models.sop import SOP
            
            db.execute(text("CREATE SCHEMA IF NOT EXISTS docucr"))
            db.commit()
            
            SOP.__table__.create(db.get_bind(), checkfirst=True)
            db.commit()
            
            return {"message": "SOP table initialized successfully"}
        except Exception as e:
            db.rollback()
            raise Exception(f"SOP table initialization failed: {str(e)}")

    @staticmethod
    def initialize_system(db: Session, super_admin_email: str, super_admin_password: str):
        """
        Initializes the system by:
        1. Creating schema and tables
        2. Seeding default statuses
        3. Seeding default modules (Definitive Dev Data)
        4. Seeding default privileges (Definitive Dev Data)
        5. Creating SUPER_ADMIN role
        6. Linking all privileges to SUPER_ADMIN role for all modules
        7. Creating the initial SUPER_ADMIN user
        """
        
        try:
            # 1. Create Schema and Tables
            db.execute(text("CREATE SCHEMA IF NOT EXISTS docucr"))
            db.commit()
            
            # Create all tables
            Base.metadata.create_all(db.get_bind())
            db.commit()
            
            # 2. Seed Statuses
            statuses = [
                {"code": "ACTIVE", "description": "Active status", "type": "USER"},
                {"code": "INACTIVE", "description": "Inactive status", "type": "USER"},
                {"code": "PENDING", "description": "Pending status", "type": "GENERAL"},
                {"code": "REJECTED", "description": "Rejected status", "type": "GENERAL"},
            ]
            
            db_statuses = {}
            for s in statuses:
                existing = db.query(Status).filter(Status.code == s["code"]).first()
                if not existing:
                    new_status = Status(
                        code=s["code"],
                        description=s["description"],
                        type=s["type"]
                    )
                    db.add(new_status)
                    db.flush()
                    db_statuses[s["code"]] = new_status
                else:
                    db_statuses[s["code"]] = existing
            
            active_status = db_statuses.get("ACTIVE")

            # 3. Seed Modules (Using Definitive Dev Data)
            modules_data = [
          {
            "id": "81a2f87b-8483-4191-97a6-1f3a86b8ba8e",
            "name": "dashboard",
            "label": "Dashboard",
            "description": "Main dashboard with overview and analytics",
            "route": "/dashboard",
            "icon": "LayoutDashboard",
            "category": "main",
            "display_order": 1,
            "color_from": "#667eea",
            "color_to": "#764ba2"
          },
          {
            "id": "75e47454-e0c0-4e52-8eb2-f7c23446c4fd",
            "name": "documents",
            "label": "Documents",
            "description": "Document management and processing",
            "route": "/documents",
            "icon": "FileText",
            "category": "main",
            "display_order": 2,
            "color_from": "#f093fb",
            "color_to": "#f5576c"
          },
          {
            "id": "921a8dff-14ee-42bd-822f-28c03f32ae1a",
            "name": "templates",
            "label": "Templates",
            "description": "Document templates and forms",
            "route": "/templates",
            "icon": "Layout",
            "category": "main",
            "display_order": 3,
            "color_from": "#4facfe",
            "color_to": "#00f2fe"
          },
          {
            "id": "61a6aeef-2378-4dae-81b6-eafba87a519a",
            "name": "sops",
            "label": "SOPs",
            "description": "Standard Operating Procedures",
            "route": "/sops",
            "icon": "BookOpen",
            "category": "main",
            "display_order": 4,
            "color_from": "#43e97b",
            "color_to": "#38f9d7"
          },
          {
            "id": "bdfac474-42ac-4233-b24b-cb167b7b034d",
            "name": "clients",
            "label": "Clients",
            "description": "Client management and information",
            "route": "/clients",
            "icon": "Users",
            "category": "main",
            "display_order": 5,
            "color_from": "#fa709a",
            "color_to": "#fee140"
          },
          {
            "id": "e518f0aa-d987-4d14-b8cc-a5abc1daeac5",
            "name": "users_permissions",
            "label": "User & Permissions",
            "description": "User management and access control",
            "route": "/users-permissions",
            "icon": "Shield",
            "category": "admin",
            "display_order": 6,
            "color_from": "#a8edea",
            "color_to": "#fed6e3"
          },
          {
            "id": "15baf30a-7ab7-4997-8086-dce65da5cac2",
            "name": "settings",
            "label": "Settings",
            "description": "System configuration and preferences",
            "route": "/settings",
            "icon": "Settings",
            "category": "admin",
            "display_order": 7,
            "color_from": "#d299c2",
            "color_to": "#fef9d7"
          },
          {
            "id": "ff2ed097-c906-4f5d-a9f0-c17a334bb7ef",
            "name": "profile",
            "label": "Profile",
            "description": "User profile and account settings",
            "route": "/profile",
            "icon": "User",
            "category": "user",
            "display_order": 8,
            "color_from": "#89f7fe",
            "color_to": "#66a6ff"
          },
          {
            "id": "e3f272ce-15d4-4cce-80e4-7d270e286336",
            "name": "form_management",
            "label": "Form Management",
            "description": "Create and manage dynamic forms",
            "route": "/forms",
            "icon": "FileEdit",
            "category": "admin",
            "display_order": 9,
            "color_from": "#ff9a9e",
            "color_to": "#fecfef"
          },
          {
            "id": "a9d7e3c1-5b7f-4f7d-8e5a-1c7a334bb7ef",
            "name": "activity_log",
            "label": "Activity Logs",
            "description": "View system activity logs",
            "route": "/activity-logs",
            "icon": "Activity",
            "category": "admin",
            "display_order": 10,
            "color_from": "#89f7fe",
            "color_to": "#66a6ff"
          }
            ]
            
            db_modules = []
            for m in modules_data:
                existing = db.query(Module).filter(Module.id == m["id"]).first()
                if not existing:
                    new_mod = Module(**m)
                    db.add(new_mod)
                    db_modules.append(new_mod)
                else:
                    db_modules.append(existing)
            db.flush()

            # 4. Seed Privileges (Using Definitive Dev Data)
            privileges_data = [
          {
            "id": "9a147d3b-81c2-4b5a-a1e6-44401bf3062f",
            "name": "CREATE",
            "description": "Create new records"
          },
          {
            "id": "50a19031-a670-417e-9dd5-13d1abdbee6d",
            "name": "READ",
            "description": "View and read records"
          },
          {
            "id": "f95fa0f7-19b1-4a0f-9747-28dcca144d4a",
            "name": "UPDATE",
            "description": "Edit and update records"
          },
          {
            "id": "68b85749-83c1-4e05-8ec4-a3e7a7fc5d3a",
            "name": "DELETE",
            "description": "Delete records"
          },
          {
            "id": "67d65b63-bb50-4627-990d-6dfbeb7da44b",
            "name": "EXPORT",
            "description": "Export data"
          },
          {
            "id": "eb43c11d-f88a-44f3-8a46-c5008f500a64",
            "name": "IMPORT",
            "description": "Import data"
          },
          {
            "id": "601cb59a-7443-4faa-b377-d53ca2d3c9fe",
            "name": "APPROVE",
            "description": "Approve workflows"
          },
          {
            "id": "d0ee2d09-1772-4961-a7fb-22e2d4508bc8",
            "name": "MANAGE",
            "description": "Full management access"
          }
            ]
            
            db_privileges = []
            for p in privileges_data:
                existing = db.query(Privilege).filter(Privilege.id == p["id"]).first()
                if not existing:
                    new_priv = Privilege(**p)
                    db.add(new_priv)
                    db_privileges.append(new_priv)
                else:
                    db_privileges.append(existing)
            db.flush()

            # 5. Create SUPER_ADMIN Role
            role_name = "SUPER_ADMIN"
            super_admin_role = db.query(Role).filter(Role.name == role_name).first()
            if not super_admin_role:
                super_admin_role = Role(
                    id=role_name,
                    name=role_name,
                    description="System administrator with full access",
                    status_id=active_status.id if active_status else None,
                    can_edit=False
                )
                db.add(super_admin_role)
                db.flush()
            
            role_id = super_admin_role.id

            # 6. Link all privileges to SUPER_ADMIN for all modules
            for mod in db_modules:
                for priv in db_privileges:
                    # Check if link exists
                    link_id = f"{role_id}_{mod.id}_{priv.id}"
                    existing_link = db.query(RoleModule).filter(RoleModule.id == link_id).first()
                    if not existing_link:
                        new_link = RoleModule(
                            id=link_id,
                            role_id=role_id,
                            module_id=mod.id,
                            privilege_id=priv.id
                        )
                        db.add(new_link)
            db.flush()

            # 7. Create/Update SUPER_ADMIN User
            existing_user = db.query(User).filter(User.email == super_admin_email.lower()).first()
            if not existing_user:
                new_user = User(
                    id=str(uuid.uuid4()),
                    email=super_admin_email.lower(),
                    username=super_admin_email.split('@')[0].lower(),
                    hashed_password=get_password_hash(super_admin_password),
                    first_name="Super",
                    last_name="Admin",
                    is_superuser=True,
                    status_id=active_status.id if active_status else None
                )
                db.add(new_user)
                db.flush()
                
                # Link to role
                user_role_link = UserRole(
                    id=str(uuid.uuid4()),
                    user_id=new_user.id,
                    role_id=role_id
                )
                db.add(user_role_link)
            else:
                # Ensure superuser and correct password
                existing_user.hashed_password = get_password_hash(super_admin_password)
                existing_user.is_superuser = True
                if active_status:
                    existing_user.status_id = active_status.id
                
                # Ensure role link exists
                existing_role_link = db.query(UserRole).filter(
                    UserRole.user_id == existing_user.id,
                    UserRole.role_id == role_id
                ).first()
                if not existing_role_link:
                    user_role_link = UserRole(
                        id=str(uuid.uuid4()),
                        user_id=existing_user.id,
                        role_id=role_id
                    )
                    db.add(user_role_link)

            db.commit()
            return {"message": "System initialized successfully with definitive seed data"}
        
        except Exception as e:
            db.rollback()
            raise Exception(f"Migration failed: {str(e)}")
