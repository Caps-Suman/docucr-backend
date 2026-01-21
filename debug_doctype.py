from pydantic import BaseModel
from typing import List
from datetime import datetime

class DocumentTypeResponse(BaseModel):
    id: str
    name: str
    description: str = ""
    status_id: int
    statusCode: str = ""
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True

class MockDocType:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

mock_obj = MockDocType(
    id="type123",
    name="Invoice",
    description="Inv desc",
    status_id=1,
    statusCode="active",
    created_at=datetime.now().isoformat(),
    updated_at=datetime.now().isoformat()
)

try:
    res = DocumentTypeResponse.model_validate(mock_obj)
    print("Validation Successful:", res)
except Exception as e:
    print("Validation Failed:", e)
