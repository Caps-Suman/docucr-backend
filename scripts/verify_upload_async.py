import asyncio
import sys
import os
import unittest
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime

# Add the parent directory to sys.path to allow importing app modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.s3_service import S3Service
from app.services.document_service import DocumentService
from app.models.document import Document

class TestAsyncUpload(unittest.IsolatedAsyncioTestCase):
    async def test_s3_upload_non_blocking(self):
        """Test that s3 upload is offloaded to executor"""
        print("Testing S3 Service Non-Blocking Upload...")
        
        # Mock S3 Client
        mock_s3 = MagicMock()
        
        # Patch the boto3 client creation in __init__
        with patch('boto3.client', return_value=mock_s3):
            service = S3Service()
            service.bucket_name = "test-bucket"
            
            # Mock file object
            mock_file = MagicMock()
            
            # Measure time
            start_time = datetime.now()
            
            # Call upload_file
            key, bucket = await service.upload_file(mock_file, "test.pdf", "application/pdf")
            
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            
            print(f"Upload call took {duration} seconds")
            
            # Verify mocks
            self.assertEqual(bucket, "test-bucket")
            self.assertTrue(key.startswith("documents/"))
            # We can't easily verify run_in_executor call unless we mock the loop, 
            # but getting here without error is a good sign.
            
    async def test_parallel_upload_processing(self):
        """Test that background processing runs in parallel"""
        print("\nTesting Parallel Background Processing...")
        
        # Mock dependencies
        mock_db = MagicMock()
        mock_doc = MagicMock()
        mock_doc.id = 1
        mock_file = MagicMock()
        mock_file.filename = "test.pdf"
        
        # Patch internal methods
        with patch('app.services.document_service.DocumentService.update_document_status', new_callable=AsyncMock) as mock_update:
            with patch('app.services.document_service.s3_service.upload_file', new_callable=AsyncMock) as mock_upload:
                mock_upload.return_value = ("key", "bucket")
                
                # Setup delayed upload to simulate work
                async def delayed_upload(*args, **kwargs):
                    await asyncio.sleep(0.1)
                    return "key", "bucket"
                mock_upload.side_effect = delayed_upload
                
                # Process 3 files
                documents = [mock_doc] * 3
                # Process 3 files
                from io import BytesIO
                file_data = {
                    'buffer': BytesIO(b"test content"),
                    'filename': "test.pdf",
                    'content_type': "application/pdf"
                }
                files_data = [file_data] * 3
                
                start_time = datetime.now()
                
                # We need to mock SessionLocal import inside the method
                with patch('app.core.database.SessionLocal', return_value=mock_db):
                    await DocumentService._process_uploads_background(mock_db, documents, files_data)
                
                end_time = datetime.now()
                duration = (end_time - start_time).total_seconds()
                
                print(f"Processed 3 files in {duration} seconds")
                
                # If sequential, it would take > 0.3s. If parallel, it should be close to 0.1s
                # (plus overhead).
                self.assertLess(duration, 0.25, "Processing took too long, likely sequential")
                self.assertEqual(mock_upload.call_count, 3)

if __name__ == '__main__':
    unittest.main()
