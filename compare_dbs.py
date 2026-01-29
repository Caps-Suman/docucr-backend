import sqlalchemy
from sqlalchemy import create_engine, inspect
import os

# Production DB (Tunnel)
PROD_DB_URL = "postgresql://docucr_user:Ighv(-ZhBkac$lVi@localhost:5344/docucr_db"

# Staging DB
STAGING_DB_URL = "postgresql://ivrocrstaging:marvel%232025@marvelsync-ivr-ocr-staging-v2.ciuwqp3kuxas.ap-south-1.rds.amazonaws.com:5432/docucr_db"

def get_schema_info(engine):
    inspector = inspect(engine)
    print(f"Schemas found: {inspector.get_schema_names()}")
    
    # Try 'public' explicitly, or first non-system schema
    schema_to_use = 'docucr'
    
    schema_info = {}
    # Use schema argument
    for table_name in inspector.get_table_names(schema=schema_to_use):
        columns = inspector.get_columns(table_name, schema=schema_to_use)
        schema_info[table_name] = {col['name']: col for col in columns}
    return schema_info

def compare_schemas():
    print("Connecting to Staging DB...")
    try:
        staging_engine = create_engine(STAGING_DB_URL)
        staging_schema = get_schema_info(staging_engine)
        print(f"Staging DB introspection complete. Found {len(staging_schema)} tables: {list(staging_schema.keys())}")
    except Exception as e:
        print(f"Failed to connect to Staging DB: {e}")
        return

    print("\nConnecting to Production DB...")
    try:
        prod_engine = create_engine(PROD_DB_URL)
        prod_schema = get_schema_info(prod_engine)
        print(f"Production DB introspection complete. Found {len(prod_schema)} tables: {list(prod_schema.keys())}")
    except Exception as e:
        print(f"Failed to connect to Production DB: {e}")
        return

    print("\n--- Comparison Results ---")
    
    all_tables = set(staging_schema.keys()) | set(prod_schema.keys())
    
    for table in sorted(all_tables):
        if table not in prod_schema:
            print(f"Table '{table}' MISSING in Production")
            continue
        if table not in staging_schema:
            print(f"Table '{table}' EXTRA in Production (not in Staging)")
            continue
            
        staging_cols = staging_schema[table]
        prod_cols = prod_schema[table]
        
        missing_in_prod = set(staging_cols.keys()) - set(prod_cols.keys())
        if missing_in_prod:
            details = []
            for col in missing_in_prod:
                col_type = staging_cols[col]['type']
                details.append(f"{col} ({col_type})")
            print(f"Table '{table}': Missing columns in Production -> {', '.join(details)}")

        # Type mismatches (simplified)
        for col in set(staging_cols.keys()) & set(prod_cols.keys()):
            s_type = str(staging_cols[col]['type'])
            p_type = str(prod_cols[col]['type'])
            if s_type != p_type:
               print(f"Table '{table}', Column '{col}': Type mismatch. Staging={s_type}, Prod={p_type}")

if __name__ == "__main__":
    compare_schemas()
