from sqlalchemy.orm import Session
from typing import List, Dict

from app.models.status import Status


class StatusService:
    @staticmethod
    def get_all_statuses(db: Session) -> List[Dict]:
        statuses = db.query(Status).all()
        return [{"id": s.id, "code": s.code, "description": s.description, "type": s.type} for s in statuses]
