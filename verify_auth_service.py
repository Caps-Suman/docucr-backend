
import os
import sys
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
load_dotenv()

from app.services.auth_service import AuthService
from app.core.database import SessionLocal

def test_auth():
    db = SessionLocal()
    email = "medexpert@gmail.com"
    password = "Default@123"
    
    print(f"Attempting to authenticate organisation: {email} / {password}")
    try:
        org = AuthService.authenticate_organisation(email, password, db)
        if org:
            print(f"SUCCESS! Authenticated organisation: {org.id}")
            
            # Check active
            is_active = AuthService.check_organisation_active(org, db)
            print(f"Is Active? {is_active}")
            
            # Check roles
            roles = AuthService.get_organisation_roles(org.id, db)
            print(f"Roles: {roles}")
        else:
            print("FAILURE: create_organisation returned None")
            
        # Check if User exists
        from app.models.user import User
        user = db.query(User).filter(User.email == email).first()
        if user:
            print(f"WARNING: User also exists with this email! User ID: {user.id}")
        else:
            print("Confirmed: No unrelated User found with this email.")
    except Exception as e:
        print(f"ERROR: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    test_auth()
