from flask import Blueprint, request, jsonify
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import random
import string

from app.core.database import SessionLocal
from app.models.user import User
from app.models.otp import OTP
from app.core.security import verify_password, create_access_token, get_password_hash
from app.utils.email import send_otp_email

auth_bp = Blueprint('auth', __name__)

def get_db():
    return SessionLocal()

@auth_bp.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')

    if not email or not password:
        return jsonify({'error': 'Email and password required'}), 400

    db = get_db()
    try:
        user = db.query(User).filter(User.email == email).first()
        if not user or not verify_password(password, user.hashed_password):
            return jsonify({'error': 'Invalid credentials'}), 401
        
        if not user.is_active:
            return jsonify({'error': 'Account is inactive'}), 403

        # Remember Me Logic
        remember_me = data.get('remember_me', False)
        expiry = timedelta(days=7) if remember_me else timedelta(minutes=30)
        
        access_token = create_access_token(
            data={"sub": user.email}, 
            expires_delta=expiry
        )
        
        return jsonify({
            'access_token': access_token, 
            'token_type': 'bearer',
            'expires_in': expiry.total_seconds(),
            'user': {
                'email': user.email,
                'first_name': user.first_name,
                'last_name': user.last_name
            }
        })
    finally:
        db.close()

@auth_bp.route('/forgot-password', methods=['POST'])
def forgot_password():
    data = request.get_json()
    email = data.get('email')

    if not email:
        return jsonify({'error': 'Email is required'}), 400

    db = get_db()
    try:
        user = db.query(User).filter(User.email == email).first()
        if not user:
            # Don't reveal user existence? Or maybe do for now for UX.
            # User asked specifically for forgot password flow.
            return jsonify({'error': 'User not found'}), 404

        # Generate OTP
        otp_code = ''.join(random.choices(string.digits, k=6))
        expires_at = datetime.utcnow() + timedelta(minutes=10)

        # Upsert OTP
        otp_record = db.query(OTP).filter(OTP.email == email).first()
        if otp_record:
            otp_record.otp_code = otp_code
            otp_record.expires_at = expires_at
            otp_record.is_used = False
        else:
            # Need ID for OTP model? It has 'id' column.
            import uuid
            new_otp = OTP(
                id=str(uuid.uuid4()),
                email=email,
                otp_code=otp_code,
                expires_at=expires_at,
                is_used=False
            )
            db.add(new_otp)
        
        db.commit()

        # Send Email
        sent = send_otp_email(email, otp_code)
        if sent:
            return jsonify({'message': 'OTP sent to your email'}), 200
        else:
            return jsonify({'message': 'Failed to send email. Check server logs.'}), 500

    except Exception as e:
        db.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()

@auth_bp.route('/reset-password', methods=['POST'])
def reset_password():
    data = request.get_json()
    email = data.get('email')
    otp_code = data.get('otp')
    new_password = data.get('new_password')

    if not email or not otp_code or not new_password:
        return jsonify({'error': 'Missing fields'}), 400

    db = get_db()
    try:
        otp_record = db.query(OTP).filter(OTP.email == email, OTP.otp_code == otp_code).first()
        
        if not otp_record:
            return jsonify({'error': 'Invalid OTP'}), 400
        
        if otp_record.is_used:
             return jsonify({'error': 'OTP already used'}), 400

        if otp_record.expires_at < datetime.utcnow():
            return jsonify({'error': 'OTP expired'}), 400

        # Update Password
        user = db.query(User).filter(User.email == email).first()
        if not user:
             return jsonify({'error': 'User not found'}), 404
        
        user.hashed_password = get_password_hash(new_password)
        otp_record.is_used = True
        
        db.commit()
        return jsonify({'message': 'Password reset successfully'}), 200

    except Exception as e:
        db.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()
