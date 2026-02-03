import pytest
from unittest.mock import patch
from fastapi import BackgroundTasks
from datetime import datetime
from uuid import uuid4

class MockObj:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

@patch("app.routers.templates_router.ActivityService.log")
@patch("app.routers.templates_router.TemplateService")
def test_create_template_activity_log(mock_template_service, mock_activity_log, client):
    # Setup
    doc_type_id = uuid4()
    template_id = uuid4()
    
    # Mock Document Type Relation
    mock_doc_type = MockObj(id=doc_type_id, name="Invoice")
    
    mock_template = MockObj(
        id=template_id,
        template_name="Test Template",
        description="A template",
        document_type_id=doc_type_id,
        status_id=1,
        statusCode="ACTIVE",
        extraction_fields=[],
        created_at=datetime.now(),
        updated_at=datetime.now(),
        document_type=mock_doc_type
    )
    
    mock_template_service.return_value.create.return_value = mock_template
    
    payload = {
        "template_name": "Test Template",
        "document_type_id": str(doc_type_id),
        "description": "A template"
    }
    
    # Act
    # We rely on conftest for dependencies.
    # Note: templates_router uses "req: Request"
    response = client.post("/api/templates/", json=payload)
    
    # Assert
    assert response.status_code == 201
    assert mock_activity_log.called
    args, kwargs = mock_activity_log.call_args
    assert kwargs['action'] == "CREATE"
    assert kwargs['entity_type'] == "template"
    assert kwargs['details']['name'] == "Test Template"
    assert "background_tasks" in kwargs

@patch("app.routers.templates_router.ActivityService.log")
@patch("app.routers.templates_router.TemplateService")
def test_update_template_activity_log(mock_template_service, mock_activity_log, client):
    # Setup
    doc_type_id = uuid4()
    template_id = uuid4()
    
    mock_doc_type = MockObj(id=doc_type_id, name="Invoice")
    
    mock_template = MockObj(
        id=template_id,
        template_name="Updated Template",
        description="Updated",
        document_type_id=doc_type_id,
        status_id=1,
        statusCode="ACTIVE",
        extraction_fields=[],
        created_at=datetime.now(),
        updated_at=datetime.now(),
        document_type=mock_doc_type
    )
    
    mock_template_service.return_value.update.return_value = mock_template
    
    payload = {
        "template_name": "Updated Template",
        "description": "Updated"
    }
    
    # Act
    response = client.put(f"/api/templates/{str(template_id)}", json=payload)
    
    # Assert
    assert response.status_code == 200
    assert mock_activity_log.called
    args, kwargs = mock_activity_log.call_args
    assert kwargs['action'] == "UPDATE"
    
@patch("app.routers.templates_router.ActivityService.log")
@patch("app.routers.templates_router.TemplateService")
def test_delete_template_activity_log(mock_template_service, mock_activity_log, client):
    # Setup
    mock_template_service.return_value.delete.return_value = None
    
    template_id = str(uuid4())
    
    # Act
    response = client.delete(f"/api/templates/{template_id}")
    
    # Assert
    assert response.status_code == 204
    assert mock_activity_log.called
    args, kwargs = mock_activity_log.call_args
    assert kwargs['action'] == "DELETE"

@patch("app.routers.templates_router.ActivityService.log")
@patch("app.routers.templates_router.TemplateService")
def test_activate_template_activity_log(mock_template_service, mock_activity_log, client):
    # Setup
    mock_template_service.return_value.activate.return_value = True
    template_id = str(uuid4())
    
    # Act
    response = client.patch(f"/api/templates/{template_id}/activate")
    
    # Assert
    assert response.status_code == 200
    assert mock_activity_log.called
    args, kwargs = mock_activity_log.call_args
    assert kwargs['action'] == "ACTIVATE"

@patch("app.routers.templates_router.ActivityService.log")
@patch("app.routers.templates_router.TemplateService")
def test_deactivate_template_activity_log(mock_template_service, mock_activity_log, client):
    # Setup
    mock_template_service.return_value.deactivate.return_value = True
    template_id = str(uuid4())
    
    # Act
    response = client.patch(f"/api/templates/{template_id}/deactivate")
    
    # Assert
    assert response.status_code == 200
    assert mock_activity_log.called
    args, kwargs = mock_activity_log.call_args
    assert kwargs['action'] == "DEACTIVATE"
