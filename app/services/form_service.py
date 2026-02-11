from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from app.models.form import Form, FormField
from app.models.status import Status
import uuid
from typing import List, Dict, Any, Optional, Tuple

class FormService:
    @staticmethod
    def get_forms(page: int, page_size: int, db: Session) -> Tuple[List[Dict], int]:
        offset = (page - 1) * page_size
        
        # We need to join Status to filter or select code.
        # Original query selected Form.status_id, which is now Integer.
        # We want to return the code.
        # So join Status and select Status.code
        query = db.query(
            Form.id,
            Form.name,
            Form.description,
            Form.status_id,
            Status.code.label('status_code'),
            Form.created_at,
            func.count(FormField.id).label('fields_count')
        ).outerjoin(FormField, Form.id == FormField.form_id)\
         .outerjoin(Status, Form.status_id == Status.id)\
         .group_by(Form.id, Form.name, Form.description, Form.status_id, Status.code, Form.created_at)\
         .order_by(Form.created_at.desc())
        
        total = query.count()
        forms = query.offset(offset).limit(page_size).all()
        
        result = []
        for row in forms:
            r = dict(row._mapping)
            # rename status_code to statusCode for frontend
            r['statusCode'] = r.pop('status_code', None)
            result.append(r)

        return result, total
    
    @staticmethod
    def get_form_stats(db: Session) -> Dict[str, int]:
        active_status = db.query(Status).filter(Status.code == 'ACTIVE').first()
        
        total_forms = db.query(func.count(Form.id)).scalar()
        active_forms = db.query(func.count(Form.id)).filter(
            Form.status_id == active_status.id if active_status else None
        ).scalar()
        
        return {
            "total_forms": total_forms or 0,
            "active_forms": active_forms or 0,
            "inactive_forms": (total_forms or 0) - (active_forms or 0)
        }
    
    @staticmethod
    def get_form_by_id(form_id: str, db: Session) -> Optional[Dict]:
        form = db.query(Form).filter(Form.id == form_id).first()
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
    def get_active_form(db: Session) -> Optional[Dict]:
        active_status = db.query(Status).filter(Status.code == 'ACTIVE').first()
        if not active_status:
            return None
        
        form = db.query(Form).filter(Form.status_id == active_status.id).first()
        if not form:
            return None
        
        return FormService.get_form_by_id(form.id, db)
    
    @staticmethod
    def create_form(data: Dict[str, Any], user_id: str, db: Session) -> Dict:
        active_status = db.query(Status).filter(Status.code == 'ACTIVE').first()
        
        # Check if there's already an active form and deactivate it
        if active_status:
            existing_active = db.query(Form).filter(Form.status_id == active_status.id).first()
            if existing_active:
                inactive_status = db.query(Status).filter(Status.code == 'INACTIVE').first()
                if inactive_status:
                    existing_active.status_id = inactive_status.id
        
        form = Form(
            id=str(uuid.uuid4()),
            name=data['name'],
            description=data.get('description'),
            status_id=active_status.id if active_status else None,
            created_by=user_id
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
        
        return FormService.get_form_by_id(form.id, db)
    
    @staticmethod
    def update_form(form_id: str, data: Dict[str, Any], db: Session) -> Optional[Dict]:
        form = db.query(Form).filter(Form.id == form_id).first()
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
        
        return FormService.get_form_by_id(form.id, db)


    
    @staticmethod
    def delete_form(form_id: str, db: Session) -> Optional[str]:
        form = db.query(Form).filter(Form.id == form_id).first()
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
