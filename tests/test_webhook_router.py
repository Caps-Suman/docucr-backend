import pytest
from unittest.mock import patch, MagicMock
from fastapi import BackgroundTasks

class MockWebhook:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

@patch("app.routers.webhook_router.ActivityService.log")
@patch("app.routers.webhook_router.webhook_service")
def test_create_webhook_activity_log(mock_webhook_service, mock_activity_log, client):
    # Setup
    mock_webhook_service.create_webhook.return_value = MockWebhook(id="webhook123", url="http://example.com", events=["create"])
    
    payload = {
        "url": "http://example.com",
        "events": ["create"]
    }
    
    # Act
    # Since we use dependency override for get_db, the permission check "profile", "UPDATE" should pass if user.is_superuser is True in conftest
    response = client.post("/api/webhooks/", json=payload)
    
    # Assert
    assert response.status_code == 200
    assert mock_activity_log.called
    args, kwargs = mock_activity_log.call_args
    assert kwargs['action'] == "CREATE"
    assert kwargs['entity_type'] == "webhook"
    assert kwargs['details']['url'] == "http://example.com"
    assert "background_tasks" in kwargs
    assert isinstance(kwargs['background_tasks'], BackgroundTasks)

@patch("app.routers.webhook_router.ActivityService.log")
@patch("app.routers.webhook_router.webhook_service")
def test_update_webhook_activity_log(mock_webhook_service, mock_activity_log, client):
    # Setup
    mock_webhook_service.update_webhook.return_value = MockWebhook(id="webhook123", url="http://example.com/updated", events=["update"])
    
    payload = {
        "url": "http://example.com/updated"
    }
    
    # Act
    response = client.patch("/api/webhooks/webhook123", json=payload)
    
    # Assert
    assert response.status_code == 200
    assert mock_activity_log.called
    args, kwargs = mock_activity_log.call_args
    assert kwargs['action'] == "UPDATE"
    assert kwargs['details']['updated_fields'] == ['url']

@patch("app.routers.webhook_router.ActivityService.log")
@patch("app.routers.webhook_router.webhook_service")
def test_delete_webhook_activity_log(mock_webhook_service, mock_activity_log, client):
    # Setup
    mock_webhook_service.delete_webhook.return_value = True
    
    # Act
    response = client.delete("/api/webhooks/webhook123")
    
    # Assert
    assert response.status_code == 200
    assert mock_activity_log.called
    args, kwargs = mock_activity_log.call_args
    assert kwargs['action'] == "DELETE"
