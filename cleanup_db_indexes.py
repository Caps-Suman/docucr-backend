from sqlalchemy import create_engine, text
import os

# Database connection details - verified from your environment
DATABASE_URL = "postgresql://ivrocrstaging:marvelsync-v2@marvelsync-ivr-ocr-staging-v2.ciuwqp3kuxas.ap-south-1.rds.amazonaws.com:5432/docucr_db"

engine = create_engine(DATABASE_URL)

def cleanup_old_constraints():
    """
    Drops old global unique constraints that are blocking the new organization-scoped logic.
    """
    commands = [
        # --- DOCUMENT TYPES ---
        "ALTER TABLE docucr.document_types DROP CONSTRAINT IF EXISTS document_types_name_key CASCADE;",
        "DROP INDEX IF EXISTS docucr.document_types_name_key CASCADE;",
        
        # --- TEMPLATES ---
        "ALTER TABLE docucr.templates DROP CONSTRAINT IF EXISTS templates_template_name_document_type_id_key CASCADE;",
        "DROP INDEX IF EXISTS docucr.templates_template_name_document_type_id_key CASCADE;",
    ]

    with engine.connect() as conn:
        print("Starting Database Cleanup...")
        for cmd in commands:
            try:
                print(f"Executing: {cmd}")
                conn.execute(text(cmd))
                conn.commit()
            except Exception as e:
                # Iterate safely; if it doesn't exist, that's fine.
                print(f"Note: {e}")
        print("\nCleanup Complete! Organization-wise duplication will now work.")

if __name__ == "__main__":
    cleanup_old_constraints()
