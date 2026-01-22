import psycopg2
import psycopg2.extras
import sys

# Connection Configs
SOURCE_DSN = 'postgresql://ivrocrstaging:marvel%232025@marvelsync-ivr-ocr-staging-v2.ciuwqp3kuxas.ap-south-1.rds.amazonaws.com:5432/docucr_db'
TARGET_DSN = 'postgresql://docucr_user:Ighv(-ZhBkac$lVi@127.0.0.1:5344/docucr_db?sslmode=disable'

TABLES = [
    {"schema": "docucr", "table": "role", "key": "name"},
    {"schema": "docucr", "table": "privilege", "key": "name"},
    {"schema": "docucr", "table": "module", "key": "name"},
    {"schema": "docucr", "table": "submodule", "key": "name"},
    {"schema": "docucr", "table": "status", "key": "code"},
]

def fetch_data(conn, schema, table, key_col):
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    try:
        query = f"SELECT * FROM {schema}.{table}"
        cursor.execute(query)
        rows = cursor.fetchall()
        data = {}
        for row in rows:
            # Convert row to dict
            r_dict = dict(row)
            # Use the key column for identification
            k = r_dict.get(key_col)
            if k:
                data[k] = r_dict
        return data
    except Exception as e:
        print(f"Error fetching {schema}.{table}: {e}")
        return {}

def compare():
    print("Connecting to Source (Staging)...")
    try:
        source_conn = psycopg2.connect(SOURCE_DSN)
        print("Connected to Source.")
    except Exception as e:
        print(f"Failed to connect to Source: {e}")
        return

    print("Connecting to Target (Production) at 127.0.0.1:5344...")
    target_conn = None
    try:
        target_conn = psycopg2.connect(
            host="127.0.0.1",
            port=5344,
            database="docucr_db",
            user="docucr_user",
            password="Ighv(-ZhBkac$lVi",
            sslmode="disable",
            connect_timeout=5
        )
        print("Connected to Target.")
    except Exception as e:
        print(f"Failed to connect to Target: {e}")
        print("\nProceeding to list Staging data for review...\n")

    for t in TABLES:
        schema = t['schema']
        table = t['table']
        key = t['key']
        
        print(f"Table: {schema}.{table} (Key: {key})")
        
        source_data = fetch_data(source_conn, schema, table, key)
        
        if not target_conn:
            print(f"-> Items in Staging: {len(source_data)}")
            for k in sorted(source_data.keys()):
                print(f"   - {k}")
        else:
            target_data = fetch_data(target_conn, schema, table, key)
            missing_in_target = []
            for k, v in source_data.items():
                if k not in target_data:
                    missing_in_target.append(v)
            
            if missing_in_target:
                print(f"-> Found {len(missing_in_target)} items missing in Production:")
                for item in missing_in_target:
                    print(f"   - {item[key]}")
            else:
                print("-> All items from Source are present in Target.")
        print("-" * 30)

    source_conn.close()
    if target_conn:
        target_conn.close()

if __name__ == "__main__":
    compare()
