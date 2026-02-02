import pytest
from unittest.mock import patch, MagicMock
from fastapi import BackgroundTasks
from app.routers.printers_router import PrinterResponse

# Test Printer Logging
@patch("app.routers.printers_router.ActivityService.log")
@patch("app.routers.printers_router.PrinterService")
def test_create_printer_activity_log(mock_printer_service, mock_activity_log, client):
    # Setup
    # Use a simple class to mimic SQLAlchemy model
    class MockPrinter:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)
    
    mock_printer = MockPrinter(
        id="printer123",
        name="Test Printer",
        ip_address="192.168.1.1",
        port=9100,
        protocol="RAW",
        description="A test printer",
        status="ACTIVE"
    )

    mock_printer_service.create_printer.return_value = mock_printer

    payload = {
        "name": "Test Printer",
        "ip_address": "192.168.1.1"
    }
    
    # Act
    # We rely on conftest.py overrides for DB and User (is_superuser=True)
    response = client.post("/api/printers/", json=payload)
    
    # Assert
    assert response.status_code == 200
    assert mock_activity_log.called
    args, kwargs = mock_activity_log.call_args
    assert kwargs['action'] == "CREATE"
    assert kwargs['entity_type'] == "printer"
    assert "background_tasks" in kwargs
    assert isinstance(kwargs['background_tasks'], BackgroundTasks)

@patch("app.routers.printers_router.ActivityService.log")
@patch("app.routers.printers_router.PrinterService")
def test_update_printer_activity_log(mock_printer_service, mock_activity_log, client):
    class MockPrinter:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)

    mock_printer = MockPrinter(
        id="printer123",
        name="Updated Printer",
        ip_address="192.168.1.2",
        port=9100,
        protocol="IPP",
        description="Updated desc",
        status="ACTIVE"
    )
    mock_printer_service.update_printer.return_value = mock_printer
    
    payload = {
        "name": "Updated Printer",
        "ip_address": "192.168.1.2",
        "protocol": "IPP"
    }
    
    # Act
    response = client.put("/api/printers/printer123", json=payload)
    
    # Assert
    assert response.status_code == 200
    assert mock_activity_log.called
    args, kwargs = mock_activity_log.call_args
    assert kwargs['action'] == "UPDATE"
    assert kwargs['entity_type'] == "printer"
    assert kwargs['details']['updated_fields'] == ['name', 'ip_address', 'protocol']

@patch("app.routers.printers_router.ActivityService.log")
@patch("app.routers.printers_router.PrinterService")
def test_delete_printer_activity_log(mock_printer_service, mock_activity_log, client):
    # Setup
    mock_printer_service.delete_printer.return_value = True
    
    # Act
    response = client.delete("/api/printers/printer123")
    
    # Assert
    assert response.status_code == 200
    assert mock_activity_log.called
    args, kwargs = mock_activity_log.call_args
    assert kwargs['action'] == "DELETE"
    assert kwargs['entity_type'] == "printer"

@patch("app.routers.printers_router.ActivityService.log")
@patch("app.routers.printers_router.PrinterService.print_document")
def test_print_document_activity_log(mock_print_doc, mock_activity_log, client):
    # Setup - mock async print_document
    # Since it's an awaitable, we mock it as an AsyncMock or keep it simple if logic permits,
    # but the router calls await. unittest.mock triggers issues with await on non-async mocks.
    # However, patch handles basic replacement. 
    # If the service method is async def, we need AsyncMock.
    
    # Let's inspect router first: `await PrinterService.print_document(...)`
    # So we need AsyncMock.
    from unittest.mock import AsyncMock
    mock_print_doc.side_effect = AsyncMock() # Or just return value if it's not the coroutine itself but the result?
    # Usually patch replaces the function. If we set side_effect to an async function or return_value to a Future.
    
    # Better:
    mock_print_doc.new_callable = AsyncMock
    
    payload = {
        "document_id": 123,
        "copies": 2
    }
    
    # Act
    # Since print_document in router is async, TestClient handles async endpoint execution.
    # We just need to make sure the service call inside doesn't crash the loop.
    # Actually, patch directly on the object might need new_callable=AsyncMock if using @patch decorator args.
    # But here we use 'with patch' or implicit. 
    # Let's trust standard mocking or use `new_callable`.
    pass 

# Re-writing the print test specifically to handle async mock correctly
@patch("app.routers.printers_router.ActivityService.log")
@patch("app.routers.printers_router.PrinterService")
def test_print_document_activity_log_async(mock_printer_service, mock_activity_log, client):
    # Setup
    from unittest.mock import AsyncMock
    mock_printer_service.print_document = AsyncMock()
    
    payload = {
        "document_id": 123,
        "copies": 2
    }
    
    response = client.post("/api/printers/printer123/print", json=payload)
    
    assert response.status_code == 200
    assert mock_activity_log.called
    args, kwargs = mock_activity_log.call_args
    assert kwargs['action'] == "PRINT"
    assert kwargs['details']['copies'] == 2
