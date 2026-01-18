-- Create document_shares table
CREATE TABLE IF NOT EXISTS docucr.document_shares (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id INTEGER NOT NULL REFERENCES docucr.documents(id) ON DELETE CASCADE,
    user_id VARCHAR NOT NULL REFERENCES docucr.user(id) ON DELETE CASCADE,
    shared_by VARCHAR NOT NULL REFERENCES docucr.user(id) ON DELETE CASCADE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    
    -- Ensure unique sharing per document-user pair
    UNIQUE(document_id, user_id)
);

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_document_shares_user_id ON docucr.document_shares(user_id);
CREATE INDEX IF NOT EXISTS idx_document_shares_document_id ON docucr.document_shares(document_id);
CREATE INDEX IF NOT EXISTS idx_document_shares_shared_by ON docucr.document_shares(shared_by);