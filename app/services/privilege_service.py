from sqlalchemy.orm import Session
from typing import List, Dict

from app.models.privilege import Privilege


class PrivilegeService:
    @staticmethod
    def get_all_privileges(db: Session) -> List[Dict]:
        privileges = db.query(Privilege).all()
        return [{"id": p.id, "name": p.name, "description": p.description} for p in privileges]
