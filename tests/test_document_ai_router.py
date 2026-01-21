from unittest.mock import patch, MagicMock, AsyncMock
from fastapi import BackgroundTasks
import os

os.environ["OPENAI_API_KEY"] = "fake-key"

@patch("app.routers.document_ai_router.ActivityService.log")
@patch("app.routers.document_ai_router.OpenAIDocumentAI")
def test_classify_document_activity_log(mock_ai_class, mock_activity_log, client):
    # Setup
    mock_ai_class.return_value.analyze = AsyncMock(return_value={
        "classification": {"document_type": "Invoice", "confidence": 0.9},
        "extraction": {}
    })
    
    # Mock file upload
    files = {'file': ('test.pdf', b'content', 'application/pdf')}
    
    # Act
    # POST /api/document-ai/classify-and-extract
    response = client.post("/api/document-ai/classify-and-extract", files=files)
    
    # Assert
    assert response.status_code == 200
    assert mock_activity_log.called
    args, kwargs = mock_activity_log.call_args
    assert kwargs['action'] == "PROCESS"
    assert kwargs['details']['filename'] == "test.pdf"
