import pytest
from starlette.testclient import TestClient
from app.main import app
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from unittest.mock import MagicMock

# Mock DB Session
def override_get_db():
    try:
        db = MagicMock()
        yield db
    finally:
        pass

# Mock Current User
def override_get_current_user():
    return User(id="test_user_id", username="testuser", first_name="Test", last_name="User", email="test@example.com", is_superuser=True)

app.dependency_overrides[get_db] = override_get_db
app.dependency_overrides[get_current_user] = override_get_current_user

@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c
