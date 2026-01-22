import psycopg2
import psycopg2.extras
import uuid

# Connection Configs
SOURCE_DSN = 'postgresql://ivrocrstaging:marvel%232025@marvelsync-ivr-ocr-staging-v2.ciuwqp3kuxas.ap-south-1.rds.amazonaws.com:5432/docucr_db'
# Using 127.0.0.1 and sslmode=disable for local tunnel robustness
TARGET_CONFIG = {
    "host": "127.0.0.1",
    "port": 5344,
    "database": "docucr_db",
    "user": "docucr_user",
    "password": "Ighv(-ZhBkac$lVi",
    "sslmode": "require",
    "connect_timeout": 60,
    "keepalives": 1
}

def sync_table(source_conn, target_conn, schema, table, pkey, columns, delete_extra=False):
    s_cur = source_conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    t_cur = target_conn.cursor()
    
    print(f"Syncing {schema}.{table}...")
    s_cur.execute(f"SELECT {', '.join(columns)} FROM {schema}.{table}")
    rows = s_cur.fetchall()
    source_ids = [row[pkey] for row in rows]
    
    if delete_extra:
        # Delete records in target that are not in source
        # WARNING: This can fail if there are foreign key constraints
        placeholders = ', '.join(['%s'] * len(source_ids))
        delete_query = f"DELETE FROM {schema}.{table} WHERE {pkey} NOT IN ({placeholders})"
        t_cur.execute(delete_query, source_ids)
        print(f"-> Deleted extra records in {table}.")

    upsert_query = f"""
    INSERT INTO {schema}.{table} ({', '.join(columns)})
    VALUES ({', '.join(['%s'] * len(columns))})
    ON CONFLICT ({pkey}) DO UPDATE SET
    {', '.join([f"{col} = EXCLUDED.{col}" for col in columns if col != pkey])}
    """
    
    for row in rows:
        t_cur.execute(upsert_query, [row[col] for col in columns])
    
    target_conn.commit()
    print(f"-> Synced {len(rows)} records in {table}.")

def sync_junction_table(source_conn, target_conn, schema, table, pkey, columns, conflict_cols):
    s_cur = source_conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    t_cur = target_conn.cursor()
    
    print(f"Syncing junction {schema}.{table}...")
    s_cur.execute(f"SELECT {', '.join(columns)} FROM {schema}.{table}")
    rows = s_cur.fetchall()
    
    upsert_query = f"""
    INSERT INTO {schema}.{table} ({', '.join(columns)})
    VALUES ({', '.join(['%s'] * len(columns))})
    ON CONFLICT ({pkey}) DO NOTHING
    """
    
    for row in rows:
        t_cur.execute(upsert_query, [row[col] for col in columns])
    
    target_conn.commit()
    print(f"-> Synced {len(rows)} records in {table}.")

def main():
    try:
        source_conn = psycopg2.connect(SOURCE_DSN)
        print("Connected to Source.")
    except Exception as e:
        print(f"Source Connection Error: {e}")
        return

    try:
        target_conn = psycopg2.connect(**TARGET_CONFIG)
        print("Connected to Target.")
    except Exception as e:
        print(f"Target Connection Error (Production Tunnel): {e}")
        source_conn.close()
        return

    try:
        t_cur = target_conn.cursor()
        
        # 0. Handle Role ID Mismatch
        print("Standardizing Role IDs in Production...")
        role_map = {
            'ADMIN': '187fb395-6a17-4ac6-ba79-fd45a1d89293',
            'SUPER_ADMIN': '0830931c-b77d-4b6f-91bf-d9ae4e173b0f'
        }
        
        # Disable constraints temporarily for the session to allow ID updates
        t_cur.execute("SET session_replication_role = 'replica';")
        try:
            for name, staging_id in role_map.items():
                t_cur.execute("SELECT id FROM docucr.role WHERE name = %s", (name,))
                prod_role = t_cur.fetchone()
                if prod_role:
                    prod_id = prod_role[0]
                    if prod_id != staging_id:
                        print(f"  Remapping {name}: {prod_id} -> {staging_id}")
                        t_cur.execute("UPDATE docucr.user_role SET role_id = %s WHERE role_id = %s", (staging_id, prod_id))
                        t_cur.execute("UPDATE docucr.role_module SET role_id = %s WHERE role_id = %s", (staging_id, prod_id))
                        t_cur.execute("UPDATE docucr.role_submodule SET role_id = %s WHERE role_id = %s", (staging_id, prod_id))
                        t_cur.execute("UPDATE docucr.role SET id = %s WHERE id = %s", (staging_id, prod_id))
            target_conn.commit()
        finally:
            t_cur.execute("SET session_replication_role = 'origin';")
        
        print("-> Role IDs standardized.")

        # 1. Status
        sync_table(source_conn, target_conn, 'docucr', 'status', 'id', ['id', 'code', 'description', 'type'])
        
        # 2. Privilege (User wants EXACT same privileges, so delete extra ones)
        s_cur = source_conn.cursor()
        s_cur.execute("SELECT id FROM docucr.privilege")
        source_priv_ids = [r[0] for r in s_cur.fetchall()]
        
        t_cur.execute("DELETE FROM docucr.role_module WHERE privilege_id NOT IN %s", (tuple(source_priv_ids),))
        t_cur.execute("DELETE FROM docucr.role_submodule WHERE privilege_id NOT IN %s", (tuple(source_priv_ids),))
        
        sync_table(source_conn, target_conn, 'docucr', 'privilege', 'id', ['id', 'name', 'description'], delete_extra=True)
        
        # 3. Module
        sync_table(source_conn, target_conn, 'docucr', 'module', 'id', 
                   ['id', 'name', 'label', 'description', 'route', 'icon', 'category', 'has_submodules', 'is_active', 'display_order'])
        
        # 4. Submodule
        sync_table(source_conn, target_conn, 'docucr', 'submodule', 'id', 
                   ['id', 'module_id', 'name', 'label', 'route_key', 'display_order'])
        
        # 5. Role
        sync_table(source_conn, target_conn, 'docucr', 'role', 'id', ['id', 'name', 'description', 'status_id', 'can_edit'])
        
        # 6. Role Permissions (Clear existing and re-sync for accuracy)
        print("Refreshing permissions...")
        t_cur.execute("DELETE FROM docucr.role_module")
        t_cur.execute("DELETE FROM docucr.role_submodule")
        
        sync_junction_table(source_conn, target_conn, 'docucr', 'role_module', 'id', ['id', 'role_id', 'module_id', 'privilege_id'], [])
        sync_junction_table(source_conn, target_conn, 'docucr', 'role_submodule', 'id', ['id', 'role_id', 'submodule_id', 'privilege_id'], [])

        print("\nSUCCESS: All master data and SUPER_ADMIN permissions synced and standardized.")

    except Exception as e:
        print(f"Sync execution error: {e}")
        target_conn.rollback()
    finally:
        source_conn.close()
        target_conn.close()

if __name__ == "__main__":
    main()
