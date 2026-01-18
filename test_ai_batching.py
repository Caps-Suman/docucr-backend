import asyncio
import os
import sys

# Add app to path
sys.path.append(os.getcwd())

from app.services.ai_service import ai_service

# Mock Schema
schemas = [
    {
        "type_name": "Invoice",
        "fields": [
            {"name": "invoice_number", "description": "Invoice number"},
            {"name": "total_amount", "description": "Total amount due"}
        ]
    }
]

async def test_progress(status, percent):
    print(f"[PROGRESS {percent}%] {status}")

async def run_test():
    file_path = "/Users/apple/Documents/OCR/docucr/docucr-backend/uploads/GREATER_WASHINGTON_ARTHRITIS_RHEUMATOLOGY_&_OSTEOPOROSIS_CTR 2.pdf"
    
    if not os.path.exists(file_path):
        print(f"File not found: {file_path}")
        return

    print(f"Loading file: {file_path}")
    with open(file_path, "rb") as f:
        content = f.read()

    print("Starting AI Analysis...")
    try:
        result = await ai_service.analyze_document(
            file_content=content,
            filename=os.path.basename(file_path),
            schemas=schemas,
            progress_callback=test_progress
        )
        print("\nAnalysis Complete!")
        print("Findings count:", len(result.get("findings", [])))
        # print("Findings:", result.get("findings")) 
    except Exception as e:
        print(f"Analysis failed: {e}")

if __name__ == "__main__":
    asyncio.run(run_test())
