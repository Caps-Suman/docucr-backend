import pytest
from unittest.mock import patch, MagicMock
from fastapi import BackgroundTasks
from app.models.user import User

class MockUser:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

@patch("app.routers.auth_router.ActivityService.log")
@patch("app.routers.auth_router.AuthService.authenticate_user")
@patch("app.core.security.create_access_token")
def test_login_activity_log(mock_create_token, mock_authenticate, mock_activity_log, client):
    # Setup
    # AuthService returns User object (SQLAlchemy model)
    mock_user = MockUser(id="user123", username="testuser", email="test@example.com", first_name="Test", last_name="User", role_id="role1", is_superuser=True, is_client=False, client_id=None)
    mock_authenticate.return_value = mock_user
    mock_create_token.return_value = "fake-token"
    
    # Also need AuthService.check_user_active -> True
    # And AuthService.get_user_roles -> List[dict]
    with patch("app.routers.auth_router.AuthService.check_user_active", return_value=True), \
         patch("app.routers.auth_router.AuthService.get_user_roles", return_value=[{"id": "role1", "name": "Admin"}]), \
         patch("app.routers.auth_router.AuthService.generate_tokens", return_value={"access_token": "token", "refresh_token": "refresh"}), \
         patch("app.routers.auth_router.AuthService.get_role_permissions", return_value={}):
    
        payload = {
            "email": "test@example.com",
            "password": "password"
        }
        
        response = client.post("/api/auth/login", json=payload)
        
        # Assert
        assert response.status_code == 200
        assert mock_activity_log.called
        args, kwargs = mock_activity_log.call_args
        assert kwargs['action'] == "LOGIN"
        assert kwargs['entity_id'] == "user123"

@patch("app.routers.auth_router.AuthService.authenticate_user")
@patch("app.routers.auth_router.AuthService.initiate_2fa")
def test_login_requires_2fa(mock_initiate, mock_authenticate, client):
    mock_user = MockUser(id="user123", email="test@example.com", is_superuser=False)
    mock_authenticate.return_value = mock_user
    mock_initiate.return_value = True
    
    with patch("app.routers.auth_router.AuthService.check_user_active", return_value=True):
        payload = {"email": "test@example.com", "password": "password"}
        response = client.post("/api/auth/login", json=payload)
        
        assert response.status_code == 200
        assert response.json()["requires_2fa"] is True
        assert mock_initiate.called

@patch("app.routers.auth_router.AuthService.verify_otp")
def test_verify_2fa_success(mock_verify, client):
    from app.main import app
    from app.core.database import get_db
    
    mock_db = MagicMock()
    app.dependency_overrides[get_db] = lambda: mock_db
    
    mock_verify.return_value = True
    mock_user = MockUser(id="user123", email="test@example.com", first_name="Test", last_name="User", is_superuser=False, is_client=False, client_id=None)
    
    with patch("app.routers.auth_router.AuthService.get_user_roles", return_value=[{"id": "role1", "name": "Admin"}]), \
         patch("app.routers.auth_router.AuthService.generate_tokens", return_value={"access_token": "token", "refresh_token": "refresh"}), \
         patch("app.routers.auth_router.AuthService.get_role_permissions", return_value={}):
        
        # Setup mock query chain
        mock_db.query.return_value.filter.return_value.first.side_effect = [mock_user, MagicMock(purpose="LOGIN")] # User followed by OTP record
        
        payload = {"email": "test@example.com", "otp": "123456"}
        response = client.post("/api/auth/verify-2fa", json=payload)
        
        # Clean up
        del app.dependency_overrides[get_db]
        
        assert response.status_code == 200
        assert "access_token" in response.json()

@patch("app.routers.auth_router.AuthService.initiate_2fa")
def test_resend_2fa(mock_initiate, client):
    from app.main import app
    from app.core.database import get_db
    
    mock_db = MagicMock()
    app.dependency_overrides[get_db] = lambda: mock_db
    
    mock_initiate.return_value = True
    mock_db.query.return_value.filter.return_value.first.return_value = MagicMock()
    
    payload = {"email": "test@example.com", "password": "password"}
    response = client.post("/api/auth/resend-2fa", json=payload)
    
    # Clean up
    del app.dependency_overrides[get_db]
    
    assert response.status_code == 200
    assert response.json()["message"] == "2FA code resent to your email"

def test_verify_2fa_fails_with_reset_otp(client):
    from app.main import app
    from app.core.database import get_db
    from app.services.auth_service import AuthService
    
    mock_db = MagicMock()
    app.dependency_overrides[get_db] = lambda: mock_db
    
    # Simulate a RESET OTP exists but we are trying to verify for LOGIN
    # verify_otp will be called with purpose="LOGIN"
    # We can either mock verify_otp or let it run against our mock_db
    
    with patch("app.routers.auth_router.AuthService.verify_otp", return_value=False) as mock_verify:
        payload = {"email": "test@example.com", "otp": "123456"}
        response = client.post("/api/auth/verify-2fa", json=payload)
        
        # Verify it was called with LOGIN purpose
        mock_verify.assert_called_with("test@example.com", "123456", mock_db, purpose="LOGIN")
        assert response.status_code == 400
        assert response.json()["detail"] == "Invalid or expired 2FA code"
    
    del app.dependency_overrides[get_db]

@patch("app.routers.auth_router.ActivityService.log")
@patch("app.services.user_service.UserService.get_user_by_email")
@patch("app.utils.email.send_otp_email")
def test_forgot_password_activity_log(mock_send_email, mock_get_user, mock_activity_log, client):
    # Setup
    mock_user = {"id": "user123", "email": "test@example.com"} # UserService usually returns dict/object depending on method, but router uses user["id"]
    mock_get_user.return_value = mock_user
    
    # We must also mock generating OTP
    with patch("app.routers.auth_router.AuthService.generate_otp", return_value="123456"):
        mock_send_email.return_value = True
        
        payload = {
            "email": "test@example.com"
        }
        
        # Act
        response = client.post("/api/auth/forgot-password", json=payload)
        
        # Assert
        assert response.status_code == 200
        assert mock_activity_log.called
        args, kwargs = mock_activity_log.call_args
        assert kwargs['action'] == "FORGOT_PASSWORD_REQUEST"
        assert kwargs['details']['email'] == "test@example.com"

@patch("app.routers.auth_router.ActivityService.log")
@patch("app.routers.auth_router.AuthService.verify_otp")
@patch("app.routers.auth_router.AuthService.reset_user_password")
def test_reset_password_activity_log(mock_reset, mock_verify, mock_activity_log, client):
    # Setup
    mock_verify.return_value = True
    mock_reset.return_value = True
    
    payload = {
        "email": "test@example.com",
        "otp": "123456",
        "new_password": "new_password"
    }
    
    # Act
    # get_user_by_email is NOT called in reset_password endpoint!
    response = client.post("/api/auth/reset-password", json=payload)
    
    # Assert
    assert response.status_code == 200
    assert mock_activity_log.called
    args, kwargs = mock_activity_log.call_args
    assert kwargs['action'] == "RESET_PASSWORD"
    assert kwargs['details']['email'] == "test@example.com"
