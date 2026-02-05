import sys
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import uuid

from dotenv import load_dotenv

# Add the parent directory to sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Load env vars
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

from app.models.module import Module
from app.models.role import Role
from app.models.role_module import RoleModule
from app.models.privilege import Privilege
from app.models.organisation import Organisation

def seed_organisation_module():
    # Database connection
    if not DATABASE_URL:
        print("DATABASE_URL not found in env")
        return
        
    engine = create_engine(DATABASE_URL)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()

    try:
        # Check if module exists
        module = db.query(Module).filter(Module.name == "organisation").first()
        if not module:
            print("Creating Organisation Module...")
            module = Module(
                id=str(uuid.uuid4()),
                name="organisation",
                label="Organisation",
                description="Manage organisations",
                route="/organisations",
                icon="Building2",
                category="admin",
                display_order=10,
                color_from="blue-500",
                color_to="cyan-500",
                is_active=True
            )
            db.add(module)
            db.commit()
            db.refresh(module)
            print(f"Module created with ID: {module.id}")
        else:
            print(f"Module already exists with ID: {module.id}")

        # specific role name
        role = db.query(Role).filter(Role.name == "SUPER_ADMIN").first()
        if not role:
            # Fallback to admin or first available role for testing if SUPER_ADMIN not found
            role = db.query(Role).first()
            if not role:
                 print("No roles found to assign module to.")
                 return
            print(f"SUPER_ADMIN not found, assigning to role: {role.name}")
        else:
            print(f"Assigning to role: {role.name}")

        # Assign privileges
        # Assuming we want all privileges for this module for the admin
        privileges = db.query(Privilege).all()
        
        for priv in privileges:
            existing_perm = db.query(RoleModule).filter(
                RoleModule.role_id == role.id,
                RoleModule.module_id == module.id,
                RoleModule.privilege_id == priv.id
            ).first()
            
            if not existing_perm:
                perm = RoleModule(
                    id=str(uuid.uuid4()),
                    role_id=role.id,
                    module_id=module.id,
                    privilege_id=priv.id
                )
                db.add(perm)
        
        db.commit()
        print("Permissions assigned successfully.")

    except Exception as e:
        print(f"Error: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    seed_organisation_module()
