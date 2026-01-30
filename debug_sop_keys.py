
import sys
import os
import json
from uuid import UUID
from datetime import datetime

sys.path.append(os.getcwd())

from app.core.database import SessionLocal
from app.models.sop import SOP

class CustomEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, UUID):
            return str(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)

def fetch_sop(sop_id):
    db = SessionLocal()
    try:
        sop = db.query(SOP).filter(SOP.id == sop_id).first()
        if not sop:
            print(json.dumps({"error": "SOP not found"}))
            return

        print("--- PROVIDER INFO KEYS ---")
        if sop.provider_info:
            print(json.dumps(sop.provider_info, indent=2))
        else:
            print("None")

        print("\n--- WORKFLOW PROCESS KEYS ---")
        if sop.workflow_process:
            print(json.dumps(sop.workflow_process, indent=2))
        else:
             print("None")

    except Exception as e:
        print(f"Error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    fetch_sop("c4cc1e79-35f6-49e6-be58-e3e2f46f0e44")
