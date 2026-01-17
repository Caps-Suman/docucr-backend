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
        
        query = db.query(
            Form.id,
            Form.name,
            Form.description,
            Form.status_id,
            Form.created_at,
            func.count(FormField.id).label('fields_count')
        ).outerjoin(FormField, Form.id == FormField.form_id)\
         .group_by(Form.id, Form.name, Form.description, Form.status_id, Form.created_at)\
         .order_by(Form.created_at.desc())
        
        total = query.count()
        forms = query.offset(offset).limit(page_size).all()
        
        return [dict(row._mapping) for row in forms], total
    
    @staticmethod
    def get_form_stats(db: Session) -> Dict[str, int]:
        active_status = db.query(Status).filter(Status.name == 'ACTIVE').first()
        
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
        
        fields = db.query(FormField).filter(FormField.form_id == form_id).order_by(FormField.order).all()
        
        return {
            "id": form.id,
            "name": form.name,
            "description": form.description,
            "status_id": form.status_id,
            "created_at": form.created_at,
            "fields": [{
                "id": f.id,
                "field_type": f.field_type,
                "label": f.label,
                "placeholder": f.placeholder,
                "required": f.required,
                "options": f.options,
                "validation": f.validation,
                "order": f.order,
                "is_system": f.is_system
            } for f in fields]
        }
    
    @staticmethod
    def get_active_form(db: Session) -> Optional[Dict]:
        active_status = db.query(Status).filter(Status.name == 'ACTIVE').first()
        if not active_status:
            return None
        
        form = db.query(Form).filter(Form.status_id == active_status.id).first()
        if not form:
            return None
        
        return FormService.get_form_by_id(form.id, db)
    
    @staticmethod
    def create_form(data: Dict[str, Any], user_id: str, db: Session) -> Dict:
        active_status = db.query(Status).filter(Status.name == 'ACTIVE').first()
        
        # Check if there's already an active form
        if active_status:
            existing_active = db.query(Form).filter(Form.status_id == active_status.id).first()
            if existing_active:
                raise ValueError("Only one form can be active at a time. Please deactivate the existing active form first.")
        
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
            active_status = db.query(Status).filter(Status.name == 'ACTIVE').first()
            if active_status and data['status_id'] == active_status.id:
                # Check if there's already another active form
                existing_active = db.query(Form).filter(
                    and_(Form.status_id == active_status.id, Form.id != form_id)
                ).first()
                if existing_active:
                    raise ValueError("Only one form can be active at a time. Please deactivate the existing active form first.")
            form.status_id = data['status_id']
        
        if 'fields' in data:
            db.query(FormField).filter(FormField.form_id == form_id).delete()
            
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
                    order=idx,
                    is_system=field_data.get('is_system', False)
                )
                db.add(field)
        
        db.commit()
        db.refresh(form)
        
        return FormService.get_form_by_id(form.id, db)
    
    @staticmethod
    def delete_form(form_id: str, db: Session) -> bool:
        form = db.query(Form).filter(Form.id == form_id).first()
        if not form:
            return False
        
        db.delete(form)
        db.commit()
        return True
    
    @staticmethod
    def check_form_name_exists(name: str, exclude_id: Optional[str], db: Session) -> bool:
        query = db.query(Form).filter(Form.name == name)
        if exclude_id:
            query = query.filter(Form.id != exclude_id)
        return query.first() is not None
