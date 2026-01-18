import sys
import os
from sqlalchemy import text

# Add current directory to path so we can import app modules
sys.path.append(os.getcwd())

from app.core.database import SessionLocal

def seed_cancelled_status():
    db = SessionLocal()
    try:
        status = {
            "id": "CANCELLED", 
            "name": "Cancelled", 
            "description": "Operation cancelled by user", 
            "type": "document"
        }
        
        # Check if exists
        result = db.execute(
            text("SELECT 1 FROM docucr.status WHERE id = :id"), 
            {"id": status["id"]}
        ).fetchone()
        
        if not result:
            print(f"Inserting status: {status['id']}")
            db.execute(
                text("""
                    INSERT INTO docucr.status (id, name, description, type, created_at, updated_at)
                    VALUES (:id, :name, :description, :type, NOW(), NOW())
                """),
                status
            )
        else:
            print(f"Status {status['id']} already exists")
            
        db.commit()
        print("Cancelled status seeding completed successfully.")
        
    except Exception as e:
        print(f"Error seeding status: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    seed_cancelled_status()
