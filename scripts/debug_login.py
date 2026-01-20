import sys
import os

# Add parent dir to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal
from app.models.user import User
from app.models.status import Status
from app.core.security import verify_password

def debug_user_login(email, password_attempt):
    db = SessionLocal()
    try:
        print(f"--- Debugging Login for {email} ---")
        
        user = db.query(User).filter(User.email == email).first()
        if not user:
            print(f"❌ User NOT FOUND with email: {email}")
            return

        print(f"✅ User found: {user.username} (ID: {user.id})")
        
        # Check Status
        if user.status_id:
            status = db.query(Status).filter(Status.id == user.status_id).first()
            if status:
                print(f"User Status: {status.code} (ID: {user.status_id})")
                if status.code != 'ACTIVE':
                    print(f"❌ User is NOT ACTIVE. Status is {status.code}")
            else:
                print(f"❓ User has status_id {user.status_id} but Status not found.")
        else:
             print("matrix User has NO status_id (Might be issue if logic requires status)")

        # Check Password
        print(f"Attempting to verify password: '{password_attempt}'")
        is_valid = verify_password(password_attempt, user.hashed_password)
        
        if is_valid:
            print("✅ Password MATCHES stored hash.")
        else:
            print("❌ Password DOES NOT match stored hash.")

    except Exception as e:
        print(f"Error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    debug_user_login("dharam@gmail.com", "1234567890")
