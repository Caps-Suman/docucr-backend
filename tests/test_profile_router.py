import pytest
from unittest.mock import patch, MagicMock
from fastapi import BackgroundTasks
from datetime import datetime

class MockUser:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

@patch("app.routers.profile_router.ActivityService.log")
@patch("app.routers.profile_router.ProfileService")
def test_update_profile_activity_log(mock_profile_service, mock_activity_log, client):
    # Setup
    # ProfileService.check_username_exists -> False
    mock_profile_service.check_username_exists.return_value = False
    mock_profile_service.update_profile.return_value = MockUser(
        id="user123", email="test@example.com", first_name="Updated", last_name="User", role_id="role1"
    )
    
    payload = {
        "first_name": "Updated",
        "last_name": "User"
    }
    
    # Act
    # Router prefix is likely /api/profile. Endpoint is /me
    response = client.put("/api/profile/me", json=payload)
    
    # Assert
    assert response.status_code == 200
    assert mock_activity_log.called
    args, kwargs = mock_activity_log.call_args
    assert kwargs['action'] == "UPDATE"
    assert "changes" in kwargs['details']

@patch("app.routers.profile_router.ActivityService.log")
@patch("app.routers.profile_router.ProfileService")
def test_change_password_activity_log(mock_profile_service, mock_activity_log, client):
    # Setup
    mock_profile_service.get_profile.return_value = MockUser(id="user123", hashed_password="old_hash")
    # verify_password might be used by ProfileService internally or router?
    # Router calls ProfileService.change_password(current_user, old, new, db)
    mock_profile_service.change_password.return_value = True
    
    payload = {
        "current_password": "old_password",
        "new_password": "new_password"
    }
    
    # Act
    response = client.post("/api/profile/change-password", json=payload)
    
    # Assert
    assert response.status_code == 200
    assert mock_activity_log.called
    args, kwargs = mock_activity_log.call_args
    assert kwargs['action'] == "UPDATE"
    assert kwargs['details']['sub_action'] == "CHANGE_PASSWORD"
