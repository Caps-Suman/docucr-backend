-- Create document_list_configs table
CREATE TABLE IF NOT EXISTS docucr.document_list_configs (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR REFERENCES docucr.user(id) NOT NULL UNIQUE,
    configuration JSONB NOT NULL,
    updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Grant privileges
GRANT ALL PRIVILEGES ON TABLE docucr.document_list_configs TO ivrocrstaging;
GRANT ALL PRIVILEGES ON SEQUENCE docucr.document_list_configs_id_seq TO ivrocrstaging;
