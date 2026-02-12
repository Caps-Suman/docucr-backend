from sqlalchemy.orm import Session
from fastapi import Request
from typing import Optional, Dict, Any
from app.models.activity_log import ActivityLog
import uuid
from app.models.organisation import Organisation
from app.models.user_role import UserRole
from app.models.role import Role
from app.models.client import Client
from app.models.user_client import UserClient
from sqlalchemy import String, cast, desc, or_

from app.models.user import User

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
    def _resolve_org_id(current_user):
        if not current_user:
            return None

        # logged in as organisation model
        if isinstance(current_user, Organisation):
            return str(current_user.id)

        # logged in as user under organisation
        if isinstance(current_user, User):
            return str(current_user.organisation_id)

        return None
    @staticmethod
    def log_task(
        action: str,
        entity_type: str,
        user_id: Optional[str] = None,
        entity_id: Optional[str] = None,
        organisation_id: Optional[str] = None,
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
                organisation_id=organisation_id,
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
        db,
        action: str,
        entity_type: str,
        entity_id: str = None,
        current_user=None,
        user_id: str = None,
        details: dict = None,
        request=None,
        background_tasks=None,
    ):
        """
        Universal activity logger.
        Handles:
        - organisation login
        - staff user
        - client user
        No endpoint changes required.
        """

        try:
            resolved_user_id = None
            resolved_org_id = None

            # ---------------------------------------
            # CASE 1: current_user passed
            # ---------------------------------------
            if current_user:

                # Organisation login
                if current_user.__class__.__name__ == "Organisation":
                    resolved_org_id = str(current_user.id)

                # User login
                else:
                    resolved_user_id = str(current_user.id)

                    if getattr(current_user, "organisation_id", None):
                        resolved_org_id = str(current_user.organisation_id)

            # ---------------------------------------
            # CASE 2: user_id manually passed
            # ---------------------------------------
            elif user_id:
                from app.models.user import User
                user = db.query(User).filter(User.id == user_id).first()

                if user:
                    resolved_user_id = str(user.id)
                    if user.organisation_id:
                        resolved_org_id = str(user.organisation_id)

            # ---------------------------------------
            # FAIL SAFE → never crash
            # ---------------------------------------
            if not resolved_user_id and not resolved_org_id:
                print("⚠️ Activity skipped: no valid actor")
                return

            from app.models.activity_log import ActivityLog

            log = ActivityLog(
                user_id=resolved_user_id,
                organisation_id=resolved_org_id,
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                details=details or {},
                ip_address=request.client.host if request else None,
                user_agent=request.headers.get("user-agent") if request else None,
            )

            db.add(log)
            db.commit()

        except Exception as e:
            print("❌ Activity log failed:", e)

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

    from sqlalchemy import String, or_, cast, desc
    @staticmethod
    def get_activity_logs(
        db: Session,
        limit: int = 50,
        offset: int = 0,
        entity_id: Optional[str] = None,
        entity_type: Optional[str] = None,
        current_user=None,
        action: Optional[str] = None,
        user_name: Optional[str] = None,
        start_date: Optional[Any] = None
    ) -> dict:

        if not current_user:
            return {"items": [], "total": 0}

        # --------------------------------------------------
        # BASE QUERY
        # --------------------------------------------------
        query = db.query(ActivityLog).join(
            User,
            ActivityLog.user_id == User.id,
            isouter=True
        ).join(
            Organisation,
            ActivityLog.organisation_id == Organisation.id,
            isouter=True
        )

        # ==================================================
        # HIERARCHY
        # ==================================================

        # -------- SUPER ADMIN → ALL --------
        if isinstance(current_user, User) and current_user.is_superuser:
            pass

        # -------- ORG LOGIN --------
        elif isinstance(current_user, Organisation):
            query = query.filter(
                ActivityLog.organisation_id == str(current_user.id)
            )

        # -------- USER LOGIN --------
        elif isinstance(current_user, User):

            # CLIENT ADMIN
            if current_user.is_client and getattr(current_user, "is_client_admin", False):

                client_user_ids = db.query(User.id).filter(
                    User.client_id == current_user.client_id
                )

                query = query.filter(
                    or_(
                        ActivityLog.user_id == str(current_user.id),
                        ActivityLog.user_id.in_(client_user_ids)
                    )
                )

            # ORG USER
            elif not current_user.is_client:
                query = query.filter(
                    ActivityLog.user_id == str(current_user.id)
                )

            # CLIENT USER
            else:
                query = query.filter(
                    ActivityLog.user_id == str(current_user.id)
                )

        # ==================================================
        # FILTERS
        # ==================================================

        if entity_id:
            query = query.filter(ActivityLog.entity_id == str(entity_id))

        if entity_type:
            query = query.filter(ActivityLog.entity_type == entity_type)

        if action:
            query = query.filter(ActivityLog.action == action)

        if start_date:
            query = query.filter(ActivityLog.created_at >= start_date)

        # 🔎 SEARCH
        if user_name:
            name = f"%{user_name}%"

            query = query.filter(
                or_(
                    User.first_name.ilike(name),
                    User.last_name.ilike(name),
                    User.email.ilike(name),
                    (User.first_name + " " + User.last_name).ilike(name),
                    Organisation.name.ilike(name)
                )
            )

        total = query.count()

        logs = (
            query.order_by(desc(ActivityLog.created_at))
            .limit(limit)
            .offset(offset)
            .all()
        )

        results = []

        for log in logs:
            user_display = "Organisation"
            email = None

            if log.user:
                parts = [
                    log.user.first_name,
                    log.user.middle_name,
                    log.user.last_name
                ]
                user_display = " ".join([p for p in parts if p]) or log.user.email
                email = log.user.email

            elif log.organisation:
                user_display = log.organisation.name

            results.append({
                "id": str(log.id),
                "name": user_display,
                "email": email,
                "action": log.action,
                "entity_type": log.entity_type,
                "entity_id": log.entity_id,
                "user_id": log.user_id,
                "organisation_id": log.organisation_id,
                "created_at": log.created_at.isoformat() if log.created_at else None,
                "details": log.details
            })

        return {
            "items": results,
            "total": total
        }

    # @staticmethod
    # def get_activity_logs(
    #     db: Session,
    #     limit: int = 50,
    #     offset: int = 0,
    #     entity_id: Optional[str] = None,
    #     entity_type: Optional[str] = None,
    #     current_user=None,
    #     action: Optional[str] = None,
    #     user_name: Optional[str] = None,
    #     start_date: Optional[Any] = None
    # ) -> dict:

    #     if not current_user:
    #         return {"items": [], "total": 0}

    #     query = db.query(ActivityLog)

    #     # =====================================================
    #     # ROLE DETECTION
    #     # =====================================================

    #     # ---------- SUPER ADMIN ----------
    #     if isinstance(current_user, User) and getattr(current_user, "is_superuser", False):
    #         pass

    #     # ---------- ORGANISATION LOGIN ----------
    #     elif isinstance(current_user, Organisation):

    #         # everything under organisation
    #         query = query.filter(
    #             ActivityLog.organisation_id == str(current_user.id)
    #         )

    #     # ---------- USER LOGIN ----------
    #     elif isinstance(current_user, User):

    #         # ---------- CLIENT ADMIN ----------
    #         if current_user.is_client and getattr(current_user, "is_client_admin", False):

    #             # get client users
    #             client_user_ids = db.query(User.id).filter(
    #                 User.client_id == current_user.client_id
    #             )

    #             query = query.filter(
    #                 or_(
    #                     ActivityLog.user_id == str(current_user.id),
    #                     ActivityLog.user_id.in_(client_user_ids)
    #                 )
    #             )

    #         # ---------- ORG USER ----------
    #         elif not current_user.is_client:
    #             query = query.filter(
    #                 ActivityLog.user_id == str(current_user.id)
    #             )

    #         # ---------- CLIENT USER ----------
    #         else:
    #             query = query.filter(
    #                 ActivityLog.user_id == str(current_user.id)
    #             )

    #     # =====================================================
    #     # OPTIONAL FILTERS
    #     # =====================================================
    #     query = db.query(ActivityLog)

    #     query = query.join(
    #         User,
    #         ActivityLog.user_id == User.id,
    #         isouter=True
    #     )

    #     query = query.join(
    #         Organisation,
    #         ActivityLog.organisation_id == Organisation.id,
    #         isouter=True
    #     )
    #     if entity_id:
    #         query = query.filter(ActivityLog.entity_id == str(entity_id))

    #     if entity_type:
    #         query = query.filter(ActivityLog.entity_type == entity_type)

    #     if action:
    #         query = query.filter(ActivityLog.action == action)

    #     if start_date:
    #         query = query.filter(ActivityLog.created_at >= start_date)

    #     if user_name:
    #         name = f"%{user_name}%"

    #         query = query.filter(
    #             or_(
    #                 User.first_name.ilike(name),
    #                 User.last_name.ilike(name),
    #                 User.email.ilike(name),

    #                 # full name search
    #                 (User.first_name + " " + User.last_name).ilike(name),

    #                 # organisation search
    #                 Organisation.name.ilike(name)
    #             )
    #         )


    #     total = query.count()

    #     logs = (
    #         query.order_by(desc(ActivityLog.created_at))
    #         .limit(limit)
    #         .offset(offset)
    #         .all()
    #     )

    #     results = []

    #     for log in logs:
    #         user_display = "Organisation"
    #         email = None

    #         if getattr(log, "user", None):
    #             parts = [
    #                 log.user.first_name,
    #                 log.user.middle_name,
    #                 log.user.last_name
    #             ]
    #             user_display = " ".join([p for p in parts if p]) or log.user.username
    #             email = log.user.email

    #         results.append({
    #             "id": str(log.id),
    #             "name": user_display,
    #             "email": email,
    #             "action": log.action,
    #             "entity_type": log.entity_type,
    #             "entity_id": log.entity_id,
    #             "user_id": log.user_id,
    #             "organisation_id": log.organisation_id,
    #             "created_at": log.created_at.isoformat() if log.created_at else None,
    #             "details": log.details
    #         })

    #     return {
    #         "items": results,
    #         "total": total
    #     }


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
