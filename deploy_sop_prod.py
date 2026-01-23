import sys
import os
from sqlalchemy import create_engine, text

# Add current directory to path so we can import app modules
sys.path.append(os.getcwd())

try:
    from app.models.sop import SOP
    from app.models.module import Base
except ImportError as e:
    print(f"Import Error: {e}")
    print("Make sure you are running this script from the docucr-backend directory.")
    sys.exit(1)

# Connection details
DATABASE_URL = "postgresql://docucr_user:Ighv(-ZhBkac$lVi@127.0.0.1:5344/docucr_db?sslmode=disable"

def deploy():
    print(f"Connecting to database via tunnel on localhost:5344...")
    # Add timeout to fail fast if stuck
    engine = create_engine(DATABASE_URL, echo=True, connect_args={'connect_timeout': 10})
    
    try:
        # Check connection
        with engine.connect() as conn:
            print("Connection successful!")
            
            # Check schema
            print("Checking schema 'docucr'...")
            result = conn.execute(text("SELECT schema_name FROM information_schema.schemata WHERE schema_name = 'docucr';"))
            if not result.scalar():
                print("Schema 'docucr' does not exist! Creating it...")
                conn.execute(text("CREATE SCHEMA docucr;"))
                conn.commit()
            
            # Check dependencies
            print("Checking dependencies...")
            client_exists = conn.execute(text("SELECT to_regclass('docucr.client');")).scalar()
            if not client_exists:
                print("WARNING: 'docucr.client' table NOT found. FK constraints might fail.")
            else:
                print("'docucr.client' found.")

            status_exists = conn.execute(text("SELECT to_regclass('docucr.status');")).scalar()
            if not status_exists:
                print("WARNING: 'docucr.status' table NOT found. FK constraints might fail.")
            else:
                print("'docucr.status' found.")
            
            print("Creating SOP table...")
            try:
                SOP.__table__.create(bind=engine)
                print("SUCCESS: SOP table created.")
            except Exception as table_err:
                if "already exists" in str(table_err):
                    print("SOP table already exists.")
                else:
                    raise table_err
            
    except Exception as e:
        print(f"Deployment Failed: {e}")

if __name__ == "__main__":
    deploy()
