-- Create user_supervisor table
CREATE TABLE IF NOT EXISTS docucr.user_supervisor (
    id VARCHAR PRIMARY KEY,
    user_id VARCHAR NOT NULL REFERENCES docucr.user(id) ON DELETE CASCADE,
    supervisor_id VARCHAR NOT NULL REFERENCES docucr.user(id) ON DELETE CASCADE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE,
    CONSTRAINT unique_user_supervisor UNIQUE (user_id)
);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_user_supervisor_user_id ON docucr.user_supervisor(user_id);
CREATE INDEX IF NOT EXISTS idx_user_supervisor_supervisor_id ON docucr.user_supervisor(supervisor_id);
