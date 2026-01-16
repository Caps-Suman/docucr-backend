-- Create status table
CREATE TABLE IF NOT EXISTS docucr.status (
    id VARCHAR PRIMARY KEY,
    name VARCHAR NOT NULL,
    description TEXT,
    type VARCHAR,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE
);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_status_name ON docucr.status(name);
CREATE INDEX IF NOT EXISTS idx_status_type ON docucr.status(type);
