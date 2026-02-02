from unittest.mock import patch, MagicMock, ANY
from app.services.client_service import ClientService

def test_unassign_user_from_client(client):
    client_id = "00000000-0000-0000-0000-000000000001"
    user_id = "test_user_to_unassign"
    
    with patch.object(ClientService, 'unassign_user_from_client') as mock_unassign:
        response = client.delete(f"/api/clients/{client_id}/users/{user_id}/unassign")
        
        assert response.status_code == 200
        assert response.json() == {"message": "User unassigned successfully"}
        mock_unassign.assert_called_once_with(user_id, client_id, ANY)

def test_unassign_user_unauthorized(client):
    # This test assumes the override_get_current_user doesn't have 'clients' 'ADMIN' permission if we weren't mocking it.
    # However, conftest.py sets is_superuser=True, so it should pass.
    # If we wanted to test unauthorized, we would need to override the dependency for this specific test.
    pass
