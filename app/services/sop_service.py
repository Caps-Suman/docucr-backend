from sqlalchemy.orm import Session
from sqlalchemy import desc
from typing import Optional, List, Dict
import uuid
from app.models.sop import SOP
from app.models.client import Client

class SOPService:
    @staticmethod
    def get_sops(db: Session, skip: int = 0, limit: int = 100) -> List[SOP]:
        return db.query(SOP).order_by(desc(SOP.created_at)).offset(skip).limit(limit).all()

    @staticmethod
    def get_sop_by_id(sop_id: str, db: Session) -> Optional[SOP]:
        return db.query(SOP).filter(SOP.id == sop_id).first()

    @staticmethod
    def create_sop(sop_data: Dict, db: Session) -> SOP:
        # Generate ID if not present (though model handles default, dict conversion might need it?)
        # Model default is usually enough.
        
        # Handling client relationship if needed
        # If client_id is empty string, set to None
        if 'client_id' in sop_data and not sop_data['client_id']:
            sop_data['client_id'] = None

        db_sop = SOP(**sop_data)
        db.add(db_sop)
        db.commit()
        db.refresh(db_sop)
        return db_sop

    @staticmethod
    def update_sop(sop_id: str, sop_data: Dict, db: Session) -> Optional[SOP]:
        db_sop = SOPService.get_sop_by_id(sop_id, db)
        if not db_sop:
            return None
        
        for key, value in sop_data.items():
            if key == 'client_id' and not value:
                 setattr(db_sop, key, None)
            else:
                setattr(db_sop, key, value)
        
        db.commit()
        db.refresh(db_sop)
        return db_sop

    @staticmethod
    def delete_sop(sop_id: str, db: Session) -> bool:
        db_sop = SOPService.get_sop_by_id(sop_id, db)
        if not db_sop:
            return False
        
        db.delete(db_sop)
        db.commit()
        return True
