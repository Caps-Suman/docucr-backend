import sys
import os

# Add parent directory to path to import app
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal
from app.models.status import Status
from sqlalchemy.exc import IntegrityError
import re

def is_uuid(code):
    uuid_pattern = re.compile(r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$')
    return bool(uuid_pattern.match(code))

from app.models.user import User
from app.models.client import Client
from app.models.role import Role
from app.models.document import Document
from app.models.document_type import DocumentType
from app.models.template import Template
from app.models.form import Form
from sqlalchemy import text

def cleanup_uuid_statuses():
    db = SessionLocal()
    try:
        # 1. Identify valid ACTIVE status to migrate to
        active_status = db.query(Status).filter(Status.code == 'ACTIVE').first()
        if not active_status:
            print("Error: Could not find 'ACTIVE' status to migrate data to.")
            return
        
        print(f"Migrating data to ACTIVE status (ID: {active_status.id})")

        # 2. Identify UUID statuses
        statuses = db.query(Status).all()
        uuid_statuses = []
        uuid_ids = []
        for s in statuses:
            if is_uuid(s.code):
                uuid_statuses.append(s)
                uuid_ids.append(s.id)
        
        if not uuid_statuses:
            print("No UUID statuses found.")
            return

        print(f"Found {len(uuid_statuses)} UUID statuses to delete: {uuid_ids}")

        # 3. Reassign references in all related tables
        # List of models to update
        models = [User, Client, Role, Document, DocumentType, Template, Form]
        
        for model in models:
            # Update rows where status_id is in uuid_ids
            # We use synchronize_session=False for bulk update
            updated_count = db.query(model).filter(model.status_id.in_(uuid_ids)).update(
                {model.status_id: active_status.id}, 
                synchronize_session=False
            )
            print(f"Updated {updated_count} rows in {model.__tablename__}")

        db.commit()

        # 4. Delete the bad statuses
        try:
            for s in uuid_statuses:
                db.delete(s)
            db.commit()
            print("Successfully deleted UUID statuses.")
        except IntegrityError as e:
            db.rollback()
            print(f"Error: Could not delete statuses due to Integrity Error (Foreign Key constraints).")
            print(f"Details: {e}")
            
    finally:
        db.close()

if __name__ == "__main__":
    cleanup_uuid_statuses()
