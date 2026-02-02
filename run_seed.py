
import os
import sys
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

sys.path.append(os.getcwd())
load_dotenv()

db_url = os.getenv('DATABASE_URL')
if db_url and '%' in db_url:
    db_url = db_url.replace('%', '%%')

engine = create_engine(db_url)

sql_file = 'scripts/seed_submodules.sql'
with open(sql_file, 'r') as f:
    sql_statements = f.read()

# Split by semicolon to execute one by one (basic split, might need more robust parsing if complex)
# or just execute block if psql supports it. SQLAlchemy execute() can handle multiple statements usually.
# But parameters might be tricky. Let's try executing the whole block.
with engine.connect() as conn:
    # Remove comments if they cause issues? SQLAlchemy text() handles them usually.
    conn.execute(text(sql_statements))
    conn.commit()
    print("Seed executed successfully.")
