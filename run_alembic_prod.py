import os
import subprocess
import sys
import urllib.parse

# Config
DB_USER = "docucr_user"
DB_PASS = "Ighv(-ZhBkac$lVi"
DB_HOST = "localhost"
DB_PORT = "5344"
DB_NAME = "docucr_db"

def run_alembic():
    # Encode password
    encoded_pass = urllib.parse.quote_plus(DB_PASS)
    db_url = f"postgresql://{DB_USER}:{encoded_pass}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    
    # Set environment variable
    env = os.environ.copy()
    env["DATABASE_URL"] = db_url
    
    # Construct command
    # Usage: python run_alembic_prod.py <alembic_args>
    # Example: python run_alembic_prod.py current
    alembic_cmd = ["venv/bin/alembic"] + sys.argv[1:]
    
    print(f"Running: {' '.join(alembic_cmd)} with DB URL set")
    
    try:
        subprocess.run(alembic_cmd, env=env, check=True)
    except subprocess.CalledProcessError as e:
        print(f"Command failed with exit code {e.returncode}")
        sys.exit(e.returncode)

if __name__ == "__main__":
    run_alembic()
