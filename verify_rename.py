
import os
import sys
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

def verify_columns():
    engine = create_engine(DATABASE_URL)
    with engine.connect() as conn:
        try:
            # Postgres specific query for columns
            query = text("SELECT column_name FROM information_schema.columns WHERE table_schema = 'docucr' AND table_name = 'user'")
            result = conn.execute(query)
            columns = [row[0] for row in result.fetchall()]
            print(f"Columns in User table: {columns}")
            
            if 'organisation_id' in columns:
                print("SUCCESS: organisation_id found in User table.")
            else:
                print("FAILURE: organisation_id NOT found.")
                
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    verify_columns()
