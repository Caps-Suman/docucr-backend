-- Create client table
CREATE TABLE IF NOT EXISTS docucr.client (
    id VARCHAR PRIMARY KEY,
    business_name VARCHAR,
    first_name VARCHAR,
    middle_name VARCHAR,
    last_name VARCHAR,
    npi VARCHAR,
    is_user BOOLEAN DEFAULT FALSE,
    type VARCHAR,
    status VARCHAR DEFAULT 'active',
    description TEXT,
    is_deleted BOOLEAN DEFAULT FALSE,
    deleted_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE
);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_client_npi ON docucr.client(npi);
CREATE INDEX IF NOT EXISTS idx_client_is_deleted ON docucr.client(is_deleted);
CREATE INDEX IF NOT EXISTS idx_client_status ON docucr.client(status);
