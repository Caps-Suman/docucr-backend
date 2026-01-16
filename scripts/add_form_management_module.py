import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
import uuid

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

def add_form_management_module():
    db = SessionLocal()
    try:
        # Check if module already exists
        result = db.execute(
            text("SELECT id FROM docucr.module WHERE name = 'Form Management'")
        ).fetchone()
        
        if result:
            print("Form Management module already exists")
            return
        
        # Get READ privilege
        read_privilege = db.execute(
            text("SELECT id FROM docucr.privilege WHERE name = 'READ'")
        ).fetchone()
        
        if not read_privilege:
            print("READ privilege not found")
            return
        
        # Insert Form Management module
        module_id = str(uuid.uuid4())
        db.execute(
            text("""
                INSERT INTO docucr.module (id, name, description, icon, route, privilege_id)
                VALUES (:id, :name, :description, :icon, :route, :privilege_id)
            """),
            {
                "id": module_id,
                "name": "Form Management",
                "description": "Create and manage dynamic forms",
                "icon": "FileText",
                "route": "/forms",
                "privilege_id": read_privilege[0]
            }
        )
        
        db.commit()
        print(f"Form Management module added successfully with ID: {module_id}")
        
    except Exception as e:
        db.rollback()
        print(f"Error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    add_form_management_module()
