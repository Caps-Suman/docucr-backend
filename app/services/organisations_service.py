from sqlalchemy.orm import Session
from sqlalchemy import func, or_
from typing import Optional, List, Dict, Tuple
import uuid
from datetime import datetime

from app.models.organisation import Organisation
from app.models.status import Status
from app.models.user_role import UserRole
from app.models.organisation_role import OrganisationRole
from app.core.security import get_password_hash

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
                    Organisation.phone_number.ilike(search_term)
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
    def create_organisation(org_data: Dict, db: Session) -> Dict:
        active_status = db.query(Status).filter(Status.code == 'ACTIVE').first()
        
        # Hash password if provided (though UI might not send it yet based on description)
        # Assuming a default password if not provided for now or handling it if provided
        print('password: ',org_data.get('password'))
        password_input = org_data.get('password')
        print('password_input: ',password_input)
        if not password_input:
            password_input = "Default@123"
        hashed_pw = get_password_hash(password_input)

        new_org = Organisation(
            id=str(uuid.uuid4()),
            email=org_data['email'],
            username=org_data['username'],
            hashed_password=hashed_pw,
            first_name=org_data['first_name'],
            middle_name=org_data.get('middle_name'),
            last_name=org_data['last_name'],
            phone_country_code=org_data.get('phone_country_code'),
            phone_number=org_data.get('phone_number'),
            status_id=active_status.id if active_status else None
        )
        
        db.add(new_org)
        db.commit()
        db.refresh(new_org)

        organisation_role_id = 'f7129eb0-7305-4279-8994-ee9256f91447'
        OrganisationService._assign_roles(new_org.id, [organisation_role_id], db)
        
        return OrganisationService._format_organisation(new_org, db)

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
            "name": f"{org.first_name} {org.middle_name + ' ' if org.middle_name else ''}{org.last_name}",
            "phone_country_code": org.phone_country_code,
            "phone_number": org.phone_number,
            "status_id": org.status_id,
            "statusCode": status_code,
            "created_at": org.created_at.isoformat() if org.created_at else None,
            "updated_at": org.updated_at.isoformat() if org.updated_at else None
        }
