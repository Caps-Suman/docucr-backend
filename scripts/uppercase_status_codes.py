import sys
import os
from sqlalchemy import text

# Add current directory to path
sys.path.append(os.getcwd())

from app.core.database import SessionLocal

def uppercase_and_drop_name():
    session = SessionLocal()
    try:
        print("Starting Status Code Standardization...")

        # 1. Update all codes to Uppercase
        print("Updating status codes to uppercase...")
        session.execute(text("UPDATE docucr.status SET code = UPPER(code)"))
        print("Status codes updated.")

        # 2. Drop name column
        print("Dropping name column...")
        session.execute(text("ALTER TABLE docucr.status DROP COLUMN name"))
        print("Name column dropped.")

        session.commit()
        print("Migration completed successfully!")

    except Exception as e:
        print(f"Migration failed: {e}")
        session.rollback()
    finally:
        session.close()

if __name__ == "__main__":
    uppercase_and_drop_name()
