import pytest
from unittest.mock import patch, MagicMock
from fastapi import BackgroundTasks

@patch("app.routers.document_list_config_router.ActivityService.log")
@patch("app.routers.document_list_config_router.DocumentListConfigService")
def test_update_config_activity_log(mock_service, mock_activity_log, client):
    # Setup
    mock_service.save_user_config.return_value = {"columns": [], "viewportWidth": 1200}
    
    payload = {
        "columns": [],
        "viewportWidth": 1200
    }
    
    # Act
    # PUT /api/document-list-config/
    # Note: user_id is inferred from current_user by router logic, path is empty
    response = client.put("/api/document-list-config/", json=payload)
    
    # Assert
    assert response.status_code == 200
    assert mock_activity_log.called
    args, kwargs = mock_activity_log.call_args
    assert kwargs['action'] == "UPDATE"
    assert kwargs['entity_type'] == "document_list_config"
    # entity_id is usually user_id
    assert "background_tasks" in kwargs

@patch("app.routers.document_list_config_router.ActivityService.log")
@patch("app.routers.document_list_config_router.DocumentListConfigService")
def test_delete_config_activity_log(mock_service, mock_activity_log, client):
    # Setup
    mock_service.delete_user_config.return_value = True
    
    # Act
    response = client.delete("/api/document-list-config/")
    
    # Assert
    assert response.status_code == 200
    assert mock_activity_log.called
    args, kwargs = mock_activity_log.call_args
    assert kwargs['action'] == "DELETE"
    assert kwargs['entity_type'] == "document_list_config"
