import pytest
from unittest.mock import patch
from fastapi import BackgroundTasks
from datetime import datetime

# NOTE: RoleService appears to return dicts, based on usage RoleResponse(**result)
class MockRole(dict):
    def __getattr__(self, name):
        if name in self:
            return self[name]
        return super().get(name)

@patch("app.routers.roles_router.ActivityService.log")
@patch("app.routers.roles_router.RoleService")
def test_create_role_activity_log(mock_role_service, mock_activity_log, client):
    # Setup
    mock_role = MockRole(
        id="role123",
        name="Test Role",
        description="A role",
        is_system_role=False,
        is_client_role=False,
        created_at=datetime.now(),
        updated_at=datetime.now(),
        role_modules=[],
        can_edit=True,
        users_count=0,
        status_id=1,
        statusCode="ACTIVE"
    )
    mock_role_service.create_role.return_value = mock_role
    mock_role_service.check_role_name_exists.return_value = False
    
    payload = {
        "name": "Test Role",
        "description": "A role",
        "privileges": []
    }
    
    # Act
    response = client.post("/api/roles/", json=payload)
    
    # Assert
    assert response.status_code == 200
    assert mock_activity_log.called
    args, kwargs = mock_activity_log.call_args
    assert kwargs['action'] == "CREATE"
    assert kwargs['entity_type'] == "role"
    assert kwargs['details']['name'] == "Test Role"
    assert "background_tasks" in kwargs

@patch("app.routers.roles_router.ActivityService.log")
@patch("app.routers.roles_router.RoleService")
def test_update_role_activity_log(mock_role_service, mock_activity_log, client):
    # Setup
    mock_role = MockRole(
        id="role123",
        name="Updated Role",
        description="Updated",
        is_system_role=False,
        is_client_role=False,
        created_at=datetime.now(),
        updated_at=datetime.now(),
        role_modules=[],
        can_edit=True,
        users_count=0,
        status_id=1,
        statusCode="ACTIVE"
    )
    
    # Mocking behaviors
    mock_role_service.get_role_by_id_simple.return_value = mock_role
    mock_role_service.check_role_name_exists.return_value = False
    mock_role_service.update_role.return_value = mock_role
    
    payload = {
        "name": "Updated Role",
        "description": "Updated"
    }
    
    # Act
    response = client.put("/api/roles/role123", json=payload)
    
    # Assert
    assert response.status_code == 200
    assert mock_activity_log.called
    args, kwargs = mock_activity_log.call_args
    assert kwargs['action'] == "UPDATE"
    assert "background_tasks" in kwargs

@patch("app.routers.roles_router.ActivityService.log")
@patch("app.routers.roles_router.RoleService")
def test_delete_role_activity_log(mock_role_service, mock_activity_log, client):
    # Setup
    mock_role_service.delete_role.return_value = (True, None)
    
    # Act
    response = client.delete("/api/roles/role123")
    
    # Assert
    assert response.status_code == 200
    assert mock_activity_log.called
    args, kwargs = mock_activity_log.call_args
    assert kwargs['action'] == "DELETE"
    assert kwargs['entity_id'] == "role123"
