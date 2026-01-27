from app.core.database import SessionLocal
from app.models.form import FormField
from sqlalchemy import select

db = SessionLocal()
try:
    # Find all fields with label 'Client'
    stmt = select(FormField.id, FormField.field_type, FormField.label).where(FormField.label == 'Client')
    results = db.execute(stmt).all()
    print("Fields with label 'Client':")
    for r in results:
        print(f"ID: {r.id}, Type: {r.field_type}, Label: {r.label}")

    # Find all unique field types
    stmt = select(FormField.field_type).distinct()
    results = db.execute(stmt).all()
    print("\nUnique field types in system:")
    for r in results:
        print(f"- {r.field_type}")
finally:
    db.close()
