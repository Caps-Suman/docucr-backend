import pytest
from unittest.mock import patch, MagicMock
from fastapi import BackgroundTasks
from datetime import datetime

class MockDocType:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

@patch("app.routers.document_types_router.ActivityService.log")
@patch("app.routers.document_types_router.DocumentTypeService")
def test_create_doctype_activity_log(mock_service, mock_activity_log, client):
    # Setup
    mock_obj = MockDocType(
        id="type123",
        name="Invoice",
        description="Inv desc",
        status_id=1,
        statusCode="active",
        created_at=datetime.now().isoformat(),
        updated_at=datetime.now().isoformat()
    )
    mock_service.return_value.create.return_value = mock_obj
    mock_service.return_value.check_name_exists.return_value = False
    
    payload = {
        "name": "Invoice",
        "description": "Inv desc"
    }
    
    # Act
    response = client.post("/api/document-types/", json=payload)
    
    # Assert
    assert response.status_code == 201
    assert mock_activity_log.called
    args, kwargs = mock_activity_log.call_args
    assert kwargs['action'] == "CREATE"
    assert kwargs['entity_type'] == "document_type"
    assert kwargs['details']['name'] == "Invoice"
    assert "background_tasks" in kwargs

@patch("app.routers.document_types_router.ActivityService.log")
@patch("app.routers.document_types_router.DocumentTypeService")
def test_update_doctype_activity_log(mock_service, mock_activity_log, client):
    # Setup
    mock_obj = MockDocType(
        id="type123",
        name="Updated Invoice",
        description="Updated",
        status_id=1,
        statusCode="active",
        created_at=datetime.now().isoformat(),
        updated_at=datetime.now().isoformat()
    )
    # Mocking behaviors in router
    mock_service.return_value.update.return_value = mock_obj
    mock_service.return_value.check_name_exists.return_value = False
    
    payload = {
        "name": "Updated Invoice",
        "description": "Updated"
    }
    
    # Act
    response = client.put("/api/document-types/type123", json=payload)
    
    # Assert
    assert response.status_code == 200
    assert mock_activity_log.called
    args, kwargs = mock_activity_log.call_args
    assert kwargs['action'] == "UPDATE"
    assert kwargs['details']['name'] == "Updated Invoice"

@patch("app.routers.document_types_router.ActivityService.log")
@patch("app.routers.document_types_router.DocumentTypeService")
def test_activate_doctype_activity_log(mock_service, mock_activity_log, client):
    mock_obj = MockDocType(
        id="type123",
        name="Invoice",
        description="Inv desc",
        status_id=1,
        statusCode="active",
        created_at=datetime.now().isoformat(),
        updated_at=datetime.now().isoformat()
    )
    mock_service.return_value.activate.return_value = mock_obj
    
    response = client.patch("/api/document-types/type123/activate")
    
    assert response.status_code == 200
    assert mock_activity_log.called
    args, kwargs = mock_activity_log.call_args
    assert kwargs['action'] == "ACTIVATE"

@patch("app.routers.document_types_router.ActivityService.log")
@patch("app.routers.document_types_router.DocumentTypeService")
def test_deactivate_doctype_activity_log(mock_service, mock_activity_log, client):
    mock_obj = MockDocType(
        id="type123",
        name="Invoice",
        description="Inv desc",
        status_id=2,
        statusCode="inactive",
        created_at=datetime.now().isoformat(),
        updated_at=datetime.now().isoformat()
    )
    mock_service.return_value.deactivate.return_value = mock_obj
    
    response = client.patch("/api/document-types/type123/deactivate")
    
    assert response.status_code == 200
    assert mock_activity_log.called
    args, kwargs = mock_activity_log.call_args
    assert kwargs['action'] == "DEACTIVATE"
    
@patch("app.routers.document_types_router.ActivityService.log")
@patch("app.routers.document_types_router.DocumentTypeService")
def test_delete_doctype_activity_log(mock_service, mock_activity_log, client):
    mock_service.return_value.delete.return_value = True
    
    response = client.delete("/api/document-types/type123")
    
    assert response.status_code == 200
    assert mock_activity_log.called
    args, kwargs = mock_activity_log.call_args
    assert kwargs['action'] == "DELETE"
