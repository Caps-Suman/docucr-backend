from flask import Blueprint, request, jsonify
from sqlalchemy.orm import Session
from sqlalchemy import and_

from app.core.database import SessionLocal
from app.models.user import User
from app.models.role import Role
from app.models.module import Module
from app.models.privilege import Privilege
from app.models.role_module import RoleModule
from app.models.user_role import UserRole
from app.models.user_role_module import UserRoleModule
from app.core.security import verify_password, create_access_token, get_password_hash

modules_bp = Blueprint('modules', __name__)

def get_db():
    return SessionLocal()

@modules_bp.route('/user-modules/<user_email>', methods=['GET'])
def get_user_modules(user_email):
    db = get_db()
    try:
        # Get user
        user = db.query(User).filter(User.email == user_email).first()
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        # Get user's accessible modules with privileges
        query = db.query(
            Module.id,
            Module.name,
            Module.label,
            Module.description,
            Module.route,
            Module.icon,
            Module.category,
            Module.display_order,
            Module.color_from,
            Module.color_to,
            Privilege.name.label('privilege_name')
        ).join(
            RoleModule, Module.id == RoleModule.module_id
        ).join(
            UserRole, RoleModule.role_id == UserRole.role_id
        ).join(
            Privilege, RoleModule.privilege_id == Privilege.id
        ).filter(
            UserRole.user_id == user.id
        ).order_by(Module.display_order)
        
        results = query.all()
        
        # Group modules with their privileges
        modules_dict = {}
        for result in results:
            module_id = result.id
            if module_id not in modules_dict:
                modules_dict[module_id] = {
                    'id': result.id,
                    'name': result.name,
                    'label': result.label,
                    'description': result.description,
                    'route': result.route,
                    'icon': result.icon,
                    'category': result.category,
                    'display_order': result.display_order,
                    'color_from': result.color_from,
                    'color_to': result.color_to,
                    'privileges': []
                }
            modules_dict[module_id]['privileges'].append(result.privilege_name)
        
        # Convert to list and sort by display_order
        modules_list = list(modules_dict.values())
        modules_list.sort(key=lambda x: x['display_order'])
        
        return jsonify({'modules': modules_list}), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()

@modules_bp.route('/user-modules', methods=['GET'])
def get_current_user_modules():
    # This would typically get user from JWT token
    # For now, using query parameter
    user_email = request.args.get('email')
    if not user_email:
        return jsonify({'error': 'Email parameter required'}), 400
    
    return get_user_modules(user_email)