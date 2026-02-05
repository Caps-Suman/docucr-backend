
import os
import sys
from sqlalchemy import create_engine, inspect
from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
load_dotenv()

from app.models.user import User

def verify_mapper():
    try:
        # Trigger mapper configuration
        from sqlalchemy.orm import configure_mappers
        configure_mappers()
        
        insp = inspect(User)
        print("User mapper initialized successfully.")
        
        # Check creator relationship
        creator_rel = insp.relationships.get('creator')
        if creator_rel:
            print(f"Creator relationship found: {creator_rel}")
            print(f"  Target: {creator_rel.mapper.class_.__name__}")
        else:
            print("ERROR: Creator relationship not found.")
            
    except Exception as e:
        print(f"Mapper Verification Failed: {e}")

if __name__ == "__main__":
    verify_mapper()
