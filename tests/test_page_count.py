import pytest
from app.services.document_service import DocumentService
from io import BytesIO
from PIL import Image
import os

def test_get_total_pages_image():
    # Simple Image
    img_content = b"fake-image-content"
    # Although we don't really parse PNG/JPG content in the method (it just returns 1),
    # let's verify it works as expected.
    count = DocumentService.get_total_pages(img_content, "image/png")
    assert count == 1
    
    count = DocumentService.get_total_pages(img_content, "image/jpeg")
    assert count == 1

def test_get_total_pages_tiff():
    # Multi-frame TIFF
    img = Image.new('RGB', (100, 100))
    img2 = Image.new('RGB', (100, 100))
    
    buf = BytesIO()
    img.save(buf, format='TIFF', save_all=True, append_images=[img2])
    tiff_content = buf.getvalue()
    
    count = DocumentService.get_total_pages(tiff_content, "image/tiff")
    assert count == 2

@pytest.mark.skipif(not os.environ.get("RUN_PDF_TESTS"), reason="Requires real PDF or mocking")
def test_get_total_pages_pdf():
    # This might require a real library or complex mock
    pass

def test_get_total_pages_docx_fallback():
    # If docx fails or it's just dummy bytes, it should return 1 (safefallback)
    count = DocumentService.get_total_pages(b"not-a-docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    assert count == 1
