-- Create documents table
CREATE TABLE IF NOT EXISTS docucr.documents (
    id SERIAL PRIMARY KEY,
    filename VARCHAR(255) NOT NULL,
    original_filename VARCHAR(255) NOT NULL,
    file_size INTEGER NOT NULL,
    content_type VARCHAR(100) NOT NULL,
    s3_key VARCHAR(500),
    s3_bucket VARCHAR(100),
    status VARCHAR(20) DEFAULT 'QUEUED' NOT NULL,
    upload_progress INTEGER DEFAULT 0,
    error_message TEXT,
    user_id VARCHAR NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES docucr.user(id)
);

-- Create index on user_id for faster queries
CREATE INDEX IF NOT EXISTS idx_documents_user_id ON docucr.documents(user_id);

-- Create index on status for filtering
CREATE INDEX IF NOT EXISTS idx_documents_status ON docucr.documents(status);

-- Create trigger to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_documents_updated_at 
    BEFORE UPDATE ON docucr.documents 
    FOR EACH ROW 
    EXECUTE FUNCTION update_updated_at_column();