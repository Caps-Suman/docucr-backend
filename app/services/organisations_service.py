from sqlalchemy.orm import Session
from sqlalchemy import func, or_
from typing import Optional, List, Dict, Tuple
import uuid
from datetime import datetime
import phonenumbers
from fastapi import HTTPException
from app.models.organisation import Organisation
from app.models.status import Status
from app.models.user_role import UserRole
from app.models.organisation_role import OrganisationRole
from app.core.security import get_password_hash
from phonenumbers import NumberParseException, PhoneNumberType

class OrganisationService:

    @staticmethod
    def get_organisations(page: int, page_size: int, search: Optional[str], status_id: Optional[str], db: Session) -> Tuple[List[Dict], int]:
        skip = (page - 1) * page_size
        
        query = db.query(Organisation)
        
        if status_id:
            query = query.join(Organisation.status_relation).filter(Status.code == status_id)
            
        if search:
            search_term = f"%{search}%"
            query = query.filter(
                or_(
                    Organisation.first_name.ilike(search_term),
                    Organisation.last_name.ilike(search_term),
                    Organisation.email.ilike(search_term),
                    Organisation.username.ilike(search_term),
                    Organisation.phone_number.ilike(search_term),
                    Organisation.name.ilike(search_term)
                )
            )
            
        total = query.count()
        organisations = query.order_by(Organisation.created_at.desc()).offset(skip).limit(page_size).all()
        
        return [OrganisationService._format_organisation(org, db) for org in organisations], total

    @staticmethod
    def get_organisation_by_id(org_id: str, db: Session) -> Optional[Dict]:
        org = db.query(Organisation).filter(Organisation.id == org_id).first()
        return OrganisationService._format_organisation(org, db) if org else None
    @staticmethod
    def validate_phone(country_code: str, phone: str) -> str:
        """
        country_code: '+91', '+1', etc
        phone: national number only (9876543210)
        returns normalized E164 number
        """

        if not phone:
            raise ValueError("Phone number required")

        if not country_code:
            raise ValueError("Country code required")

        # remove +
        cc = country_code.replace("+", "").strip()

        # combine
        full_number = f"+{cc}{phone}"

        # hard safety check (prevents 50 digit junk)
        if len(phone) > 15:
            raise ValueError("Phone number too long")

        try:
            parsed = phonenumbers.parse(full_number, None)
        except NumberParseException:
            raise ValueError("Invalid phone format")

        # possible length for that country
        if not phonenumbers.is_possible_number(parsed):
            raise ValueError("Invalid length for country")

        # real telecom validation
        if not phonenumbers.is_valid_number(parsed):
            raise ValueError("Invalid phone for country")

        # OPTIONAL: only allow mobile numbers
        number_type = phonenumbers.number_type(parsed)
        if number_type not in (
            PhoneNumberType.MOBILE,
            PhoneNumberType.FIXED_LINE_OR_MOBILE,
        ):
            raise ValueError("Only mobile numbers allowed")

        return phonenumbers.format_number(
            parsed,
            phonenumbers.PhoneNumberFormat.E164
        )

    @staticmethod
    def create_organisation(org_data: Dict, db: Session) -> Dict:
        active_status = db.query(Status).filter(Status.code == "ACTIVE").first()

        # password
        password_input = org_data.get("password") or "Default@123"
        hashed_pw = get_password_hash(password_input)

        new_org = Organisation(
            id=str(uuid.uuid4()),
            name=org_data["name"],
            email=org_data["email"],
            username=org_data["username"],
            hashed_password=hashed_pw,
            first_name=org_data.get("first_name"),
            middle_name=org_data.get("middle_name"),
            last_name=org_data.get("last_name"),
            phone_country_code=org_data.get("phone_country_code"),
            phone_number=org_data.get("phone_number"),
            status_id=active_status.id if active_status else None,
        )

        db.add(new_org)
        db.commit()
        db.refresh(new_org)

        # return {
        #     "id": new_org.id,
        #     "name": new_org.name,
        #     "email": new_org.email,
        #     "username": new_org.username,
        #     "first_name": new_org.first_name,
        #     "last_name": new_org.last_name,
        #     "status_id": new_org.status_id,
        # }
        return new_org


    @staticmethod
    def _assign_roles(org_id: str, role_ids: List[str], db: Session):
        for role_id in role_ids:
            org_role = OrganisationRole(
                id=str(uuid.uuid4()),
                organisation_id=org_id,
                role_id=role_id
            )
            db.add(org_role)
        db.commit()

    @staticmethod
    def update_organisation(org_id: str, org_data: Dict, db: Session) -> Optional[Dict]:
        org = db.query(Organisation).filter(Organisation.id == org_id).first()
        if not org:
            return None
            
        for key, value in org_data.items():
            if key == 'password' and value:
                org.hashed_password = get_password_hash(value)
            elif key != 'id':
                setattr(org, key, value)
                
        db.commit()
        db.refresh(org)
        return OrganisationService._format_organisation(org, db)

    @staticmethod
    def deactivate_organisation(org_id: str, db: Session) -> Optional[Dict]:
        org = db.query(Organisation).filter(Organisation.id == org_id).first()
        if not org:
            return None
            
        inactive_status = db.query(Status).filter(Status.code == 'INACTIVE').first()
        if inactive_status:
            org.status_id = inactive_status.id
            db.commit()
            db.refresh(org)
            
        return OrganisationService._format_organisation(org, db)

    @staticmethod
    def get_organisation_stats(db: Session) -> Dict:
        base_query = db.query(Organisation)
        total = base_query.count()
        
        active_status = db.query(Status).filter(Status.code == 'ACTIVE').first()
        inactive_status = db.query(Status).filter(Status.code == 'INACTIVE').first()
        
        active = base_query.filter(Organisation.status_id == active_status.id).count() if active_status else 0
        inactive = base_query.filter(Organisation.status_id == inactive_status.id).count() if inactive_status else 0
        
        return {
            "total_organisations": total,
            "active_organisations": active,
            "inactive_organisations": inactive
        }

    @staticmethod
    def check_email_exists(email: str, exclude_id: Optional[str], db: Session) -> bool:
        query = db.query(Organisation).filter(Organisation.email == email)
        if exclude_id:
            query = query.filter(Organisation.id != exclude_id)
        return query.first() is not None

    @staticmethod
    def check_username_exists(username: str, exclude_id: Optional[str], db: Session) -> bool:
        query = db.query(Organisation).filter(Organisation.username == username)
        if exclude_id:
            query = query.filter(Organisation.id != exclude_id)
        return query.first() is not None

    @staticmethod
    def _format_organisation(org: Organisation, db: Session) -> Dict:
        status_code = None
        if org.status_relation:
            status_code = org.status_relation.code
        elif org.status_id:
             status_obj = db.query(Status).filter(Status.id == org.status_id).first()
             if status_obj:
                 status_code = status_obj.code

        return {
            "id": org.id,
            "email": org.email,
            "username": org.username,
            "first_name": org.first_name,
            "middle_name": org.middle_name,
            "last_name": org.last_name,
            "name": org.name, # Use DB column
            "phone_country_code": org.phone_country_code,
            "phone_number": org.phone_number,
            "status_id": org.status_id,

            "statusCode": status_code,
            "created_at": org.created_at.isoformat() if org.created_at else None,
            "updated_at": org.updated_at.isoformat() if org.updated_at else None
        }
    @staticmethod
    def change_password(org_id: str, new_password: str, db: Session) -> bool:
        org = db.query(Organisation).filter(Organisation.id == org_id).first()
        if not org:
            return False
        
        org.hashed_password = get_password_hash(new_password)
        db.commit()
        return True
