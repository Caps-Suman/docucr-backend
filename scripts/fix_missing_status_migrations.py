import sys
import os
from sqlalchemy import text

# Add current directory to path
sys.path.append(os.getcwd())

from app.core.database import SessionLocal

def fix_missing_migrations():
    session = SessionLocal()
    try:
        print("Starting Fix for Missing Status Migrations (DocumentTypes, Forms, Templates)...")

        tables = ['docucr.document_types', 'docucr.form', 'docucr.templates']

        for table in tables:
            print(f"Processing table {table}...")
            
            # 1. Add temporary int column
            session.execute(text(f"ALTER TABLE {table} ADD COLUMN status_id_int INTEGER"))
            
            # 2. Update int column by mapping string status_id to Status.id (via code)
            # Note: The old string IDs in these tables are likely lowercase 'active', but Status.code is now UPPERCASE 'ACTIVE'.
            # So we match by UPPER(table.status_id) = Status.code
            query = text(f"""
                UPDATE {table}
                SET status_id_int = s.id
                FROM docucr.status s
                WHERE UPPER({table}.status_id) = s.code
            """)
            session.execute(query)
            
            # 3. Drop old string column
            session.execute(text(f"ALTER TABLE {table} DROP COLUMN status_id"))
            
            # 4. Rename new column
            session.execute(text(f"ALTER TABLE {table} RENAME COLUMN status_id_int TO status_id"))
            
            # 5. Add FK constraint
            # Constraint name convention: fk_tablename_status
            short_table = table.split('.')[1]
            session.execute(text(f"""
                ALTER TABLE {table} 
                ADD CONSTRAINT fk_{short_table}_status 
                FOREIGN KEY (status_id) REFERENCES docucr.status(id)
            """))
            print(f"Table {table} fixed.")

        session.commit()
        print("Fix Migrations completed successfully!")

    except Exception as e:
        print(f"Migration failed: {e}")
        session.rollback()
    finally:
        session.close()

if __name__ == "__main__":
    fix_missing_migrations()
