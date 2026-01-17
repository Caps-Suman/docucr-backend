-- Create user_client mapping table
CREATE TABLE IF NOT EXISTS docucr.user_client (
    id VARCHAR PRIMARY KEY,
    user_id VARCHAR NOT NULL REFERENCES docucr.user(id) ON DELETE CASCADE,
    client_id VARCHAR NOT NULL REFERENCES docucr.client(id) ON DELETE CASCADE,
    assigned_by VARCHAR REFERENCES docucr.user(id) ON DELETE SET NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, client_id)
);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_user_client_user_id ON docucr.user_client(user_id);
CREATE INDEX IF NOT EXISTS idx_user_client_client_id ON docucr.user_client(client_id);
