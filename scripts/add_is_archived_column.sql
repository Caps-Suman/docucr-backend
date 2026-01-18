-- Add is_archived column to documents table
ALTER TABLE docucr.documents 
ADD COLUMN is_archived BOOLEAN DEFAULT FALSE NOT NULL;

-- Update existing archived documents based on status
UPDATE docucr.documents 
SET is_archived = TRUE 
WHERE status_id = (SELECT id FROM docucr.status WHERE code = 'ARCHIVED');

-- Create index for better query performance
CREATE INDEX idx_documents_is_archived ON docucr.documents(is_archived);