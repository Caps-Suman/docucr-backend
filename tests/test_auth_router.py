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
    mock_user = MockUser(id="user123", username="testuser", email="test@example.com", first_name="Test", last_name="User", role_id="role1")
    mock_authenticate.return_value = mock_user
    mock_create_token.return_value = "fake-token"
    
    # Also need AuthService.check_user_active -> True
    # And AuthService.get_user_roles -> List[dict]
    with patch("app.routers.auth_router.AuthService.check_user_active", return_value=True), \
         patch("app.routers.auth_router.AuthService.get_user_roles", return_value=[{"id": "role1", "name": "Admin"}]), \
         patch("app.routers.auth_router.AuthService.generate_tokens", return_value={"access_token": "token", "refresh_token": "refresh"}):
    
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
