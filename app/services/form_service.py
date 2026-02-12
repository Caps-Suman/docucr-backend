from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from app.models.form import Form, FormField
from app.models.organisation import Organisation
from app.models.status import Status
import uuid
from typing import List, Dict, Any, Optional, Tuple

from app.models.user import User

class FormService:
    @staticmethod
    def _resolve_org_id(current_user):
        if not current_user:
            return None

        # superadmin handled separately
        if getattr(current_user, "is_superuser", False):
            return None

        if isinstance(current_user, Organisation):
            return str(current_user.id)

        if isinstance(current_user, User):
            return str(current_user.organisation_id) if current_user.organisation_id else None

        return None

    @staticmethod
    def _apply_access_filter(query, current_user):

        # SUPERADMIN → unrestricted
        if getattr(current_user, "is_superuser", False):
            return query

        org_id = FormService._resolve_org_id(current_user)

        # no org → no access (client / random user)
        if not org_id:
            return query.filter(False)

        return query.filter(Form.organisation_id == org_id)

    @staticmethod
    def get_form_stats(db: Session, current_user) -> Dict[str, int]:

        # CLIENT → no access
        if getattr(current_user, "is_client", False):
            return {
                "total_forms": 0,
                "active_forms": 0,
                "inactive_forms": 0
            }

        active_status = db.query(Status).filter(Status.code == 'ACTIVE').first()

        # base query
        total_query = db.query(func.count(Form.id))
        active_query = db.query(func.count(Form.id))

        # apply hierarchy filter
        total_query = FormService._apply_access_filter(total_query, current_user)

        if active_status:
            active_query = active_query.filter(Form.status_id == active_status.id)
        else:
            active_query = active_query.filter(False)

        active_query = FormService._apply_access_filter(active_query, current_user)

        total_forms = total_query.scalar() or 0
        active_forms = active_query.scalar() or 0

        return {
            "total_forms": total_forms,
            "active_forms": active_forms,
            "inactive_forms": total_forms - active_forms
        }


    @staticmethod
    def get_forms(page, page_size, db, current_user, status=None):

        offset = (page - 1) * page_size
        from sqlalchemy.orm import aliased

        UserAlias = aliased(User)
        OrgAlias = aliased(Organisation)

        query = db.query(
            Form.id,
            Form.name,
            Form.description,
            Form.status_id,
            Status.code.label("status_code"),
            Form.created_at,
            Form.created_by,
            Form.organisation_id,
            OrgAlias.name.label("organisation_name"),
            UserAlias.first_name.label("user_first_name"),
            UserAlias.last_name.label("user_last_name"),
            func.count(FormField.id).label("fields_count")
        ).outerjoin(FormField, Form.id == FormField.form_id)\
        .outerjoin(Status, Form.status_id == Status.id)\
        .outerjoin(OrgAlias, Form.organisation_id == OrgAlias.id)\
        .outerjoin(UserAlias, Form.created_by == UserAlias.id)\
        .group_by(
            Form.id,
            Status.code,
            OrgAlias.name,
            UserAlias.first_name,
            UserAlias.last_name
        )\
        .order_by(Form.created_at.desc())

        # hierarchy filter
        query = FormService._apply_access_filter(query, current_user)

        # status filter
        if status:
            status_obj = db.query(Status).filter(Status.code == status).first()
            if status_obj:
                query = query.filter(Form.status_id == status_obj.id)

        total = query.count()
        rows = query.offset(offset).limit(page_size).all()

        result = []

        for row in rows:
            r = dict(row._mapping)

            if r.get("user_first_name"):
                r["created_by_name"] = f"{r['user_first_name']} {r['user_last_name']}"
                r["creator_type"] = "user"

            elif r.get("organisation_name"):
                r["created_by_name"] = r["organisation_name"]
                r["creator_type"] = "organisation"

            else:
                r["created_by_name"] = "Unknown"
                r["creator_type"] = "unknown"

            r["statusCode"] = r.pop("status_code", None)

            result.append(r)

        return result, total

    
    @staticmethod
    def get_form_by_id(form_id: str, db: Session, current_user:str) -> Optional[Dict]:
        # form = db.query(Form).filter(Form.id == form_id).first()
        # if not form:
        #     return None
        query = db.query(Form).filter(Form.id == form_id)
        query = FormService._apply_access_filter(query, current_user)

        form = query.first()
        if not form:
            return None
        fields = db.query(FormField).filter(FormField.form_id == str(form_id)).order_by(FormField.order).all()
        status_code = form.status_relation.code if form.status_relation else None

        return {
            "id": form.id,
            "name": form.name,
            "description": form.description,
            "status_id": form.status_id,
            "statusCode": status_code,
            "created_at": form.created_at,
            "fields": [{
                "id": f.id,
                "field_type": f.field_type,
                "label": f.label,
                "placeholder": f.placeholder,
                "required": f.required,
                "options": f.options,
                "validation": f.validation,
                "default_value": f.default_value,  # 👈 ADD
                "order": f.order,
                "is_system": f.is_system
            } for f in fields]
        }
    
    @staticmethod
    def get_active_form(db: Session, current_user:str) -> Optional[Dict]:
        active_status = db.query(Status).filter(Status.code == 'ACTIVE').first()
        if not active_status:
            return None
        
        form = db.query(Form).filter(Form.status_id == active_status.id).first()
        if not form:
            return None
        
        return FormService.get_form_by_id(form.id, db, current_user)
    
    @staticmethod
    def create_form(data: Dict[str, Any], user_id: str, db: Session, current_user:str) -> Dict:

        active_status = db.query(Status).filter(Status.code == "ACTIVE").first()
        inactive_status = db.query(Status).filter(Status.code == "INACTIVE").first()

        org_id = FormService._resolve_org_id(current_user)
        if not org_id:
            raise PermissionError("No access")

        # deactivate existing active form for THIS org
        if active_status and inactive_status:
            existing_active = db.query(Form).filter(
                Form.organisation_id == org_id,
                Form.status_id == active_status.id
            ).first()

            if existing_active:
                existing_active.status_id = inactive_status.id

        # creator handling
        creator_id = None

        if isinstance(current_user, User):
            creator_id = str(current_user.id)

        elif isinstance(current_user, Organisation):
            creator_id = str(current_user.id)

        form = Form(
            id=str(uuid.uuid4()),
            name=data['name'],
            description=data.get('description'),
            organisation_id=org_id,
            status_id=active_status.id if active_status else None,
            created_by=creator_id
        )
        db.add(form)
        
        fields = data.get('fields', [])
        for idx, field_data in enumerate(fields):
            field = FormField(
                id=str(uuid.uuid4()),
                form_id=form.id,
                field_type=field_data['field_type'],
                label=field_data['label'],
                placeholder=field_data.get('placeholder'),
                required=field_data.get('required', False),
                options=field_data.get('options'),
                validation=field_data.get('validation'),
                default_value=field_data.get('default_value'),  # 👈 ADD
                order=idx,
                is_system=field_data.get('is_system', False)
            )
            db.add(field)
        
        db.commit()
        db.refresh(form)
        
        return FormService.get_form_by_id(form.id,db,current_user)
    
    @staticmethod
    def update_form(form_id: str, data: Dict[str, Any], db: Session, current_user:str) -> Optional[Dict]:
        form_query = db.query(Form).filter(Form.id == form_id)
        form_query = FormService._apply_access_filter(form_query, current_user)

        form = form_query.first()
        if not form:
            return None

        if 'name' in data:
            form.name = data['name']
        if 'description' in data:
            form.description = data['description']
        if 'status_id' in data:
            # Check if trying to activate this form
            active_status = db.query(Status).filter(Status.code == 'ACTIVE').first()
            
            # Map input status code (potentially string) to ID if needed, but here logic compares IDs? 
            # `data['status_id']` from frontend is string code ('ACTIVE').
            # We must resolve it.
            status_code_input = data['status_id']
            status_obj = db.query(Status).filter(Status.code == status_code_input).first()
            
            if status_obj:
                 new_status_id = status_obj.id
                 
                 if active_status and new_status_id == active_status.id:
                    # Deactivate all other forms first
                    inactive_status = db.query(Status).filter(Status.code == 'INACTIVE').first()
                    if inactive_status:
                        db.query(Form).filter(
                            and_(Form.status_id == active_status.id, Form.id != form_id)
                        ).update({Form.status_id: inactive_status.id})
                 
                 form.status_id = new_status_id

        if 'fields' in data:
            db.query(FormField).filter(FormField.form_id == str(form_id)).delete()
            
            for idx, field_data in enumerate(data['fields']):
                field = FormField(
                    id=str(uuid.uuid4()),
                    form_id=form.id,
                    field_type=field_data['field_type'],
                    label=field_data['label'],
                    placeholder=field_data.get('placeholder'),
                    required=field_data.get('required', False),
                    options=field_data.get('options'),
                    validation=field_data.get('validation'),
                    default_value=field_data.get('default_value'),  # 👈 ADD
                    order=idx,
                    is_system=field_data.get('is_system', False)
                )
                db.add(field)
        
        db.commit()
        db.refresh(form)
        
        return FormService.get_form_by_id(form.id, db, current_user)


    
    @staticmethod
    def delete_form(form_id: str, db: Session, current_user:str) -> Optional[str]:
        form_query = db.query(Form).filter(Form.id == form_id)
        form_query = FormService._apply_access_filter(form_query, current_user)

        form = form_query.first()
        if not form:
            return None

        
        name = form.name
        db.delete(form)
        db.commit()
        return name
    
    @staticmethod
    def check_form_name_exists(name: str, exclude_id: Optional[str], db: Session) -> bool:
        query = db.query(Form).filter(Form.name == name)
        if exclude_id:
            query = query.filter(Form.id != exclude_id)
        return query.first() is not None
