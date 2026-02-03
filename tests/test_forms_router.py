import pytest
from unittest.mock import patch, MagicMock
from fastapi import BackgroundTasks
from datetime import datetime

class MockForm:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

@patch("app.routers.forms_router.ActivityService.log")
@patch("app.routers.forms_router.FormService")
def test_create_form_activity_log(mock_form_service, mock_activity_log, client):
    # Setup
    mock_form = MockForm(
        id="form123",
        name="Test Form",
        description="A form",
        status_id=1,
        created_at=datetime.now(),
        fields=[{"field_type": "text", "label": "Name"}]
    )
    mock_form_service.create_form.return_value = mock_form
    mock_form_service.check_form_name_exists.return_value = False
    
    payload = {
        "name": "Test Form",
        "description": "A form",
        "fields": [{"field_type": "text", "label": "Name"}]
    }
    
    # Act
    # get_current_user returns a dict/user object? 
    # In conftest we return a User object. 
    # The endpoint definition: current_user: dict = Depends(get_current_user). 
    # Wait, in forms_router.py: current_user: dict = Depends(get_current_user).
    # But in other routers it is User object. The get_current_user returns User object.
    # Why is it typed as dict?
    # If it is typed as dict but receives User object, Pydantic/FastAPI might not care at runtime if used as object?
    # Or does it fail? 
    # Let's see forms_router.py line 111: current_user: dict
    # But usage: current_user.id
    # If valid runtime object, typing hint doesn't crash python.
    
    response = client.post("/api/forms/", json=payload)
    
    # Assert
    assert response.status_code == 200
    assert mock_activity_log.called
    args, kwargs = mock_activity_log.call_args
    assert kwargs['action'] == "CREATE"
    assert kwargs['entity_type'] == "form"
    assert kwargs['details']['name'] == "Test Form"
    assert "background_tasks" in kwargs

@patch("app.routers.forms_router.ActivityService.log")
@patch("app.routers.forms_router.FormService")
def test_update_form_activity_log(mock_form_service, mock_activity_log, client):
    # Setup
    mock_form = MockForm(
        id="form123",
        name="Updated Form",
        description="Updated",
        status_id=1,
        created_at=datetime.now(),
        fields=[]
    )
    mock_form_service.update_form.return_value = mock_form
    mock_form_service.check_form_name_exists.return_value = False
    
    payload = {
        "name": "Updated Form",
        "description": "Updated"
    }
    
    # Act
    response = client.put("/api/forms/form123", json=payload)
    
    # Assert
    assert response.status_code == 200
    assert mock_activity_log.called
    args, kwargs = mock_activity_log.call_args
    assert kwargs['action'] == "UPDATE"
    assert kwargs['details']['updated_fields'] == ['name', 'description']

@patch("app.routers.forms_router.ActivityService.log")
@patch("app.routers.forms_router.FormService")
def test_delete_form_activity_log(mock_form_service, mock_activity_log, client):
    # Setup
    mock_form_service.delete_form.return_value = True
    
    # Act
    response = client.delete("/api/forms/form123")
    
    # Assert
    assert response.status_code == 200
    assert mock_activity_log.called
    args, kwargs = mock_activity_log.call_args
    assert kwargs['action'] == "DELETE"
