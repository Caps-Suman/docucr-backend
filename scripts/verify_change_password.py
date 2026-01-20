import sys
import os
import requests

# Add parent dir to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal
from app.models.user import User
from app.core.security import get_password_hash, verify_password

def verify_change_password():
    db = SessionLocal()
    try:
        print("--- Verifying Change Password Feature ---")
        
        # 1. Create a dummy test user manually
        test_email = "test_cp_user@example.com"
        initial_password = "OldPassword123!"
        
        # Cleanup if exists
        db.query(User).filter(User.email == test_email).delete()
        db.commit()
        
        print(f"Creating test user: {test_email}")
        user = User(
            id="test_cp_uid_123",
            email=test_email,
            username="test_cp_user",
            first_name="Test",
            last_name="User",
            hashed_password=get_password_hash(initial_password),
            is_superuser=False
        )
        db.add(user)
        db.commit()
        
        # 2. Simulate Backend Service Call directly (Mocking Admin Action)
        # We are testing the service logic primarily, and the DB update.
        # Ideally we would call the API, but we need auth token for that.
        # Let's test the Service method directly first.
        
        from app.services.user_service import UserService
        
        new_password = "NewPassword456!"
        print(f"Changing password to: {new_password}")
        success = UserService.change_password(user.id, new_password, db)
        
        if not success:
            print("❌ Service returned False")
            return

        db.refresh(user)
        
        # 3. Verify
        if verify_password(new_password, user.hashed_password):
            print("✅ Password verification passed!")
        else:
            print("❌ Password verification FAILED.")

        # 4. Verify Old Password Fails
        if not verify_password(initial_password, user.hashed_password):
            print("✅ Old password correctly rejected.")
        else:
            print("❌ Old password still works (Unexpected).")

    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        # Cleanup
        db.query(User).filter(User.email == "test_cp_user@example.com").delete()
        db.commit()
        db.close()

if __name__ == "__main__":
    verify_change_password()
