from sqlalchemy.orm import Session
from fastapi import Request
from typing import Optional, Dict, Any
from app.models.activity_log import ActivityLog
import uuid

class ActivityService:
    @staticmethod
    def _normalize_value(value: Any) -> Any:
        if value is None:
            return None
        if hasattr(value, "isoformat"):  # datetime
            return value.isoformat()
        if hasattr(value, "__str__") and not isinstance(value, (int, float, bool, str)):
            return str(value)
        return value

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
        if exclude is None:
            exclude = []

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
                    changes[key] = {
                        "from": ActivityService._normalize_value(old_val),
                        "to": ActivityService._normalize_value(new_val)
                    }
        
        return changes

    
    # -------------------------------------------------------------------------
    # PART 2: Scalable Action Handling (Reading & Formatting)
    # -------------------------------------------------------------------------

    ACTION_CONFIG = {
        "create": {
            "label": "Create",
            "template": "{user} created this {entity}"
        },
        "view": {
            "label": "View",
            "template": "{user} viewed this {entity}"
        },
        "update": {
            "label": "Update",
            "template": "{user} updated this {entity}"
        },
        "delete": {
            "label": "Delete",
            "template": "{user} deleted this {entity}"
        },
        "print": {
            "label": "Print",
            "template": "{user} printed this {entity}"
        },
        "share": {
            "label": "Share",
            "template": "{user} shared this {entity}"
        },
        "archive": {
            "label": "Archive",
            "template": "{user} archived this {entity}"
        },
        "download": {
            "label": "Download",
            "template": "{user} downloaded this {entity}"
        },
        "login": {
            "label": "Login",
            "template": "{user} logged in"
        },
        "logout": {
            "label": "Logout",
            "template": "{user} logged out"
        },
        "restore": {
            "label": "Restore",
            "template": "{user} restored this {entity}"
        },
        # Add more actions here as needed
    }

    @staticmethod
    def get_activity_logs(
        db: Session,
        limit: int = 50,
        offset: int = 0,
        entity_id: Optional[str] = None,
        entity_type: Optional[str] = None,
        action: Optional[str] = None,
        user_name: Optional[str] = None,
        start_date: Optional[Any] = None # datetime
    ) -> dict:
        """
        Fetches activity logs filtered by entity, joins user data,
        and generates human-readable descriptions.
        """
        from app.models.user import User  # Avoid circular import
        from sqlalchemy import desc

        # 1. Fetch Logs (Query builder)
        query = db.query(ActivityLog)
        
        if entity_id:
            query = query.filter(ActivityLog.entity_id == str(entity_id))
        
        if entity_type:
            query = query.filter(ActivityLog.entity_type == entity_type)
            
        if action:
            query = query.filter(ActivityLog.action == action)
            
        if start_date:
            query = query.filter(ActivityLog.created_at >= start_date)

        # Join User
        query = query.join(User, ActivityLog.user_id == User.id, isouter=True) 

        if user_name:
            query = query.filter(
                (User.first_name.ilike(f"%{user_name}%")) | 
                (User.last_name.ilike(f"%{user_name}%")) | 
                (User.username.ilike(f"%{user_name}%")) | 
                (User.email.ilike(f"%{user_name}%"))
            )
        
        total = query.count()
        logs = query.order_by(desc(ActivityLog.created_at)).limit(limit).offset(offset).all()

        results = []
        for log in logs:
            # 2. Build User Name
            user_name_display = "System"
            user_email = None
            user_phone = None
            
            if log.user:
                parts = [
                    log.user.first_name,
                    log.user.middle_name, # Assuming it exists, if not it will be ignored by filter
                    log.user.last_name
                ]
                # Filter None or empty strings
                user_name_display = " ".join([p for p in parts if p]) or log.user.username or "Unknown User"
                user_email = log.user.email
                user_phone = getattr(log.user, "phone", None) # Safe access

            # 3. Generate Description
            description = ActivityService._generate_description(log, user_name_display)

            # 4. Map to DTO Structure
            results.append({
                "id": str(log.id),
                "name": user_name_display,
                "email": user_email,
                "phone": user_phone,
                "action": log.action,
                "action_label": ActivityService.ACTION_CONFIG.get(log.action, {}).get("label", log.action.capitalize()),
                "entity_type": log.entity_type,
                "entity_id": log.entity_id,
                "entity_name": None, # Could resolve if needed, but costly
                "user_id": log.user_id,
                "description": description,
                "created_at": log.created_at.isoformat() if log.created_at else None,
                "details": log.details
            })

        return {
            "items": results,
            "total": total
        }

    @staticmethod
    def _generate_description(log: ActivityLog, user_name: str) -> str:
        """
        Generates dynamic description based on ACTION_CONFIG.
        """
        action_key = log.action
        config = ActivityService.ACTION_CONFIG.get(action_key)
        
        entity_name = log.entity_type.capitalize() # Default entity name
        
        # If we had entity name resolution logic (fetching the document name), we could use it here.
        # For now, using generic "document" or entity_type is safer/faster than N+1 queries.
        # But for 'details', we can interpolate.
        
        template = "{user} performed {action} on this {entity}" # Fallback
        
        if config and "template" in config:
            template = config["template"]
            
        # Context for formatting
        context = {
            "user": user_name,
            "entity": entity_name,
            "action": action_key,
        }
        
        # Flatten details into context for simpler templates (e.g. {printer_id})
        if log.details and isinstance(log.details, dict):
            for k, v in log.details.items():
                context[k] = v
                
        try:
            return template.format(**context)
        except KeyError:
             # Fallback if template expects keys not in details
            return f"{user_name} performed '{action_key}' on this {entity_name}"
