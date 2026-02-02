from unittest.mock import patch, MagicMock, AsyncMock
from app.services.document_service import DocumentService
from app.models.document import Document
from app.models.form import FormField
import pytest
import json

def test_extract_client_id_from_form_data():
    db = MagicMock()
    form_data = {"field_1": "client_uuid_123"}
    
    # Mock FormField
    mock_field = MagicMock(spec=FormField)
    mock_field.id = "field_1"
    mock_field.field_type = "client_dropdown"
    mock_field.label = "Client"
    
    db.query.return_value.filter.return_value.first.return_value = mock_field
    
    client_id = DocumentService.extract_client_id_from_form_data(db, form_data)
    assert client_id == "client_uuid_123"

@pytest.mark.asyncio
async def test_process_multiple_uploads_maps_client():
    db = MagicMock()
    # Create fake files
    files = [MagicMock()]
    files[0].filename = "test.pdf"
    files[0].size = 100
    files[0].content_type = "application/pdf"
    files[0].read = AsyncMock(return_value=b"test content")
    files[0].seek = AsyncMock()
    
    user_id = "test_user_id"
    form_data = json.dumps({"field_1": "client_uuid_123"})
    
    # Mocking necessary methods and dependencies
    with patch("app.services.document_service.DocumentService.get_status_id_by_code", return_value=1), \
         patch("app.services.document_service.DocumentService.extract_client_id_from_form_data", return_value="client_uuid_123"), \
         patch("app.services.document_service.websocket_manager.broadcast_document_status", new_callable=AsyncMock), \
         patch("app.services.document_service.asyncio.create_task") as mock_create_task:
        
        # We need to mock the Document constructor to return a mock that we can inspect
        with patch("app.services.document_service.Document", side_effect=lambda **kwargs: MagicMock(**kwargs, spec=Document)):
            docs = await DocumentService.process_multiple_uploads(db, files, user_id, form_data=form_data)
            
            assert len(docs) == 1
            assert docs[0].client_id == "client_uuid_123"

def test_update_document_form_data_maps_client(client):
    document_id = 1
    form_data = {"field_1": "client_uuid_123"}
    
    # Mock the DB session used by the router
    from app.core.database import get_db
    
    mock_db = MagicMock()
    
    # Mock document
    mock_doc = MagicMock(spec=Document)
    mock_doc.id = document_id
    mock_doc.filename = "test.pdf"
    mock_doc.client_id = None
    mock_doc.form_data_relation = MagicMock()
    mock_doc.form_data_relation.data = {}
    
    # Mock field
    mock_field = MagicMock(spec=FormField)
    mock_field.label = "Client"
    mock_field.field_type = "client_dropdown"
    mock_field.options = []
    
    # Setup a very permissive side effect for query
    def query_side_effect(*args, **kwargs):
        m = MagicMock()
        # Handle chain: db.query(...).join(...).join(...).filter(...).all()
        m.join.return_value = m
        m.filter.return_value = m
        m.all.return_value = [MagicMock(name="ADMIN")] # Assume admin
        # Handle chain: db.query(...).filter(...).first()
        # Check if we are querying FormField vs Document
        if args and "FormField" in str(args[0]):
            m.filter.return_value.first.return_value = mock_field
        else:
            m.filter.return_value.first.return_value = mock_doc
        return m

    mock_db.query.side_effect = query_side_effect
    
    # Override the get_db dependency
    from app.main import app
    app.dependency_overrides[get_db] = lambda: mock_db
    
    try:
        with patch("app.routers.documents_router.DocumentService.extract_client_id_from_form_data", return_value="client_uuid_123"), \
             patch("app.routers.documents_router.ActivityService.log"), \
             patch("app.routers.documents_router.ActivityService.calculate_changes", return_value={}):
            
            response = client.patch(f"/api/documents/{document_id}/form-data", json=form_data)
            
            assert response.status_code == 200
            assert mock_doc.client_id == "client_uuid_123"
            assert mock_db.commit.called
    finally:
        app.dependency_overrides[get_db] = get_db
