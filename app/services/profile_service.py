from sqlalchemy.orm import Session
from typing import Dict, Optional

from app.models.user import User
from app.core.security import get_password_hash, verify_password


class ProfileService:
    @staticmethod
    def get_profile(user: User) -> Dict:
        return {
            "id": user.id,
            "email": user.email,
            "username": user.username,
            "first_name": user.first_name,
            "middle_name": user.middle_name,
            "last_name": user.last_name,
            "phone_country_code": user.phone_country_code,
            "phone_number": user.phone_number,
            "is_superuser": user.is_superuser,
            "created_at": user.created_at,
            "profile_image_url": user.profile_image_url
        }

    @staticmethod
    def update_profile(user: User, profile_data: Dict, db: Session) -> bool:
        for key, value in profile_data.items():
            if value is not None:
                setattr(user, key, value)
        db.commit()
        db.refresh(user)
        return True

    @staticmethod
    def change_password(user: User, current_password: str, new_password: str, db: Session) -> bool:
        if not verify_password(current_password, user.hashed_password):
            return False
        user.hashed_password = get_password_hash(new_password)
        db.commit()
        return True

    @staticmethod
    def check_username_exists(username: str, exclude_id: str, db: Session) -> bool:
        return db.query(User).filter(User.username == username, User.id != exclude_id).first() is not None

    @staticmethod
    def update_avatar(user: User, profile_image_url: str, db: Session) -> bool:
        user.profile_image_url = profile_image_url
        db.commit()
        db.refresh(user)
        return True
