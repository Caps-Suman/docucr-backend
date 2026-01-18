#!/usr/bin/env python3
"""
Add is_archived column to documents table
"""
import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import engine
from sqlalchemy import text

def run_migration():
    """Run the migration to add is_archived column"""
    
    migration_sql = """
    -- Add is_archived column to documents table
    ALTER TABLE docucr.documents 
    ADD COLUMN IF NOT EXISTS is_archived BOOLEAN DEFAULT FALSE NOT NULL;

    -- Update existing archived documents based on status
    UPDATE docucr.documents 
    SET is_archived = TRUE 
    WHERE status_id = (SELECT id FROM docucr.status WHERE code = 'ARCHIVED');

    -- Create index for better query performance
    CREATE INDEX IF NOT EXISTS idx_documents_is_archived ON docucr.documents(is_archived);
    """
    
    try:
        with engine.connect() as connection:
            # Execute each statement separately
            statements = [stmt.strip() for stmt in migration_sql.split(';') if stmt.strip()]
            
            for statement in statements:
                if statement:
                    print(f"Executing: {statement[:50]}...")
                    connection.execute(text(statement))
            
            connection.commit()
            print("✅ Migration completed successfully!")
            
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        return False
    
    return True

if __name__ == "__main__":
    run_migration()