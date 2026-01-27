import psycopg2
import urllib.parse

# Prod Config
PROD_CONFIG = {
    "host": "localhost",
    "port": 5344,
    "database": "docucr_db",
    "user": "docucr_user",
    "password": "Ighv(-ZhBkac$lVi"
}

# Staging Config
# URL: postgresql://ivrocrstaging:marvel%232025@marvelsync-ivr-ocr-staging-v2.ciuwqp3kuxas.ap-south-1.rds.amazonaws.com:5432/docucr_db
# Decoding password: marvel%232025 -> marvel#2025
STAGING_CONFIG = {
    "host": "marvelsync-ivr-ocr-staging-v2.ciuwqp3kuxas.ap-south-1.rds.amazonaws.com",
    "port": 5432,
    "database": "docucr_db",
    "user": "ivrocrstaging",
    "password": "marvel#2025"
}

def get_db_schema(config, env_name):
    try:
        conn = psycopg2.connect(**config)
        cur = conn.cursor()
        print(f"Connected to {env_name}")
        
        # Debug: List schemas
        cur.execute("SELECT schema_name FROM information_schema.schemata;")
        schemas = [row[0] for row in cur.fetchall()]
        print(f"Available schemas in {env_name}: {schemas}")

        # Debug: List sample tables
        cur.execute("SELECT table_schema, table_name FROM information_schema.tables LIMIT 10;")
        tables = cur.fetchall()
        print(f"Sample tables in {env_name}: {tables}")

        # Get all columns (try public first, but if empty, maybe we need to adjust)
        query = """
        SELECT table_name, column_name, data_type
        FROM information_schema.columns
        WHERE table_schema = 'docucr'
        ORDER BY table_name, column_name;
        """
        cur.execute(query)
        rows = cur.fetchall()
        
        schema = {}
        for table, col, dtype in rows:
            if table not in schema:
                schema[table] = {}
            schema[table][col] = dtype
            
        cur.close()
        conn.close()
        return schema
    except Exception as e:
        print(f"Failed to connect to {env_name}: {e}")
        return None

def compare_schemas(prod, staging):
    print("\n--- Comparison Results (Missing in PROD) ---\n")
    
    missing_tables = []
    missing_columns = {}
    
    # Check tables
    for table in staging:
        if table not in prod:
            missing_tables.append(table)
        else:
            # Check columns
            prod_cols = prod[table]
            staging_cols = staging[table]
            
            table_missing_cols = []
            for col in staging_cols:
                if col not in prod_cols:
                    table_missing_cols.append(f"{col} ({staging_cols[col]})")
            
            if table_missing_cols:
                missing_columns[table] = table_missing_cols

    if missing_tables:
        print(f"MISSING TABLES ({len(missing_tables)}):")
        for t in missing_tables:
            print(f"- {t}")
    else:
        print("All tables from Staging exist in Prod.")
        
    print("\n")
    
    if missing_columns:
        print(f"MISSING COLUMNS in existing tables:")
        for table, cols in missing_columns.items():
            print(f"Table '{table}':")
            for c in cols:
                print(f"  - {c}")
    else:
        print("All columns from Staging tables exist in Prod tables.")

if __name__ == "__main__":
    print("Fetching Staging Schema...")
    staging = get_db_schema(STAGING_CONFIG, "Staging")
    
    print("Fetching Prod Schema...")
    prod = get_db_schema(PROD_CONFIG, "Prod")
    
    if staging is not None and prod is not None:
        print(f"Staging tables found: {len(staging)}")
        print(f"Prod tables found: {len(prod)}")
        compare_schemas(prod, staging)
    else:
        print("One or both schema retrievals failed/returned None.")
