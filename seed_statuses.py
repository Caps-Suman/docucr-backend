import sys
import os
from sqlalchemy import text

# Add current directory to path so we can import app modules
sys.path.append(os.getcwd())

from app.core.database import SessionLocal

def seed_statuses():
    db = SessionLocal()
    try:
        statuses = [
            {
                "id": "AI_QUEUED", 
                "name": "AI Queued", 
                "description": "Document queued for AI analysis", 
                "type": "document"
            },
            {
                "id": "ANALYZING", 
                "name": "Analyzing", 
                "description": "Document is being analyzed by AI", 
                "type": "document"
            }
        ]
        
        for status in statuses:
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
        print("Status seeding completed successfully.")
        
    except Exception as e:
        print(f"Error seeding statuses: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    seed_statuses()
