import os
import sys
import asyncio
from io import BytesIO

# Add project root to path
sys.path.append(os.getcwd())

from app.core.database import SessionLocal
from app.models.document import Document
from app.services.document_service import DocumentService
from app.services.s3_service import s3_service

async def backfill_async():
    db = SessionLocal()
    try:
        # Query documents with missing page count
        docs = db.query(Document).filter(Document.total_pages == 0).all()
        print(f"Found {len(docs)} documents to backfill.")
        
        for idx, doc in enumerate(docs):
            print(f"[{idx+1}/{len(docs)}] Processing {doc.filename} (ID: {doc.id})...")
            
            if not doc.s3_key:
                print(f"  Skip: No S3 key for document {doc.id}")
                continue
                
            try:
                # Download from S3 (async)
                content = await s3_service.download_file(doc.s3_key)
                if not content:
                    print(f"  Error: Could not download {doc.s3_key}")
                    continue
                    
                # Calculate pages
                pages = DocumentService.get_total_pages(content, doc.content_type)
                print(f"  Result: {pages} pages")
                
                # Update
                doc.total_pages = pages
                
                # Check for commit interval
                if (idx + 1) % 10 == 0:
                    db.commit()
                    print("  Intermediate commit")
                    
            except Exception as e:
                print(f"  Error processing {doc.filename}: {str(e)}")
        
        db.commit()
        print("Backfill completed successfully.")
        
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(backfill_async())
