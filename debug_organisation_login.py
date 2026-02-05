
import os
import sys
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
from passlib.context import CryptContext

# Add parent directory
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def debug_organisations():
    if not DATABASE_URL:
        print("DATABASE_URL not found")
        return

    engine = create_engine(DATABASE_URL)
    with engine.connect() as conn:
        print("\n--- Checking Organisation Table ---")
        try:
            result = conn.execute(text("SELECT email, username, hashed_password, status_id FROM docucr.organisation"))
            rows = result.fetchall()
            
            if not rows:
                print("No organisations found in the database.")
            else:
                print(f"Found {len(rows)} organisations:")
                for row in rows:
                    email, username, hashed_password, status_id = row
                    print(f"Email: {email}, Username: {username}, Status ID: {status_id}")
                    print(f"Hash Start: {hashed_password[:10]}...")
                    
                    # Test default password
                    is_valid = verify_password("Default@123", hashed_password)
                    print(f"Is 'Default@123' valid? {is_valid}")
                    
        except Exception as e:
            print(f"Error querying table: {e}")

if __name__ == "__main__":
    debug_organisations()
