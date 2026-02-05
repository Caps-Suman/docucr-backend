
import os
import sys
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

def verify_role_columns():
    engine = create_engine(DATABASE_URL)
    with engine.connect() as conn:
        try:
            query = text("SELECT column_name FROM information_schema.columns WHERE table_schema = 'docucr' AND table_name = 'role'")
            result = conn.execute(query)
            columns = [row[0] for row in result.fetchall()]
            print(f"Columns in Role table: {columns}")
            
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    verify_role_columns()
