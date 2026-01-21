from sqlalchemy.orm import Session
from fastapi import Request
from typing import Optional, Dict, Any
from app.models.activity_log import ActivityLog
import uuid

class ActivityService:
    @staticmethod
    def log_task(
        action: str,
        entity_type: str,
        user_id: Optional[str] = None,
        entity_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ):
        """
        Background task to write activity log.
        Creates its own DB session to ensure persistence after request logic finishes.
        """
        from app.core.database import SessionLocal
        db = SessionLocal()
        try:
            activity_entry = ActivityLog(
                id=uuid.uuid4(),
                user_id=user_id,
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                details=details,
                ip_address=ip_address,
                user_agent=user_agent
            )
            db.add(activity_entry)
            db.commit()
        except Exception as e:
            print(f"Failed to write background activity log: {e}")
            db.rollback()
        finally:
            db.close()

    @staticmethod
    def log(
        db: Session, # Kept for backward compatibility if needed, though we prefer background_tasks
        action: str,
        entity_type: str,
        entity_id: Optional[str] = None,
        user_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        request: Optional[Request] = None,
        background_tasks: Optional[Any] = None # Support FastAPI BackgroundTasks
    ):
        """
        Logs an action. Prefer using `background_tasks` for zero-latency.
        """
        ip_address = None
        user_agent = None

        if request:
            ip_address = request.client.host if request.client else None
            user_agent = request.headers.get("user-agent")

        if background_tasks:
            # Zero-latency: Offload to background
            background_tasks.add_task(
                ActivityService.log_task,
                action=action,
                entity_type=entity_type,
                user_id=user_id,
                entity_id=entity_id,
                details=details,
                ip_address=ip_address,
                user_agent=user_agent
            )
            return None
        else:
            # Fallback: Synchronous write (Blocking)
            activity_entry = ActivityLog(
                id=uuid.uuid4(),
                user_id=user_id,
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                details=details,
                ip_address=ip_address,
                user_agent=user_agent
            )
            db.add(activity_entry)
            try:
                db.commit()
                db.refresh(activity_entry)
                return activity_entry
            except Exception as e:
                print(f"Failed to write activity log: {e}")
                db.rollback()
                return None

    @staticmethod
    def calculate_changes(old_obj: Any, new_data: Dict[str, Any], exclude: list = None) -> Dict[str, Dict[str, Any]]:
        """
        Calculates changes between an SQLAlchemy object (or dict) and a dictionary of new data.
        Returns a dictionary of changes: {field: {'from': old_val, 'to': new_val}}
        """
        exclude = exclude or []
        changes = {}
        
        is_dict = isinstance(old_obj, dict)
        
        for key, new_val in new_data.items():
            if key in exclude:
                continue
            
            old_val = None
            has_field = False
            
            if is_dict:
                if key in old_obj:
                    old_val = old_obj[key]
                    has_field = True
            elif hasattr(old_obj, key):
                old_val = getattr(old_obj, key)
                has_field = True
                
            if has_field:
                # Handle simple comparison
                if old_val != new_val:
                    changes[key] = {"from": old_val, "to": new_val}
                    
        return changes
