-- Update documents table to use status_id foreign key
ALTER TABLE docucr.documents DROP COLUMN IF EXISTS status;
ALTER TABLE docucr.documents ADD COLUMN status_id VARCHAR REFERENCES docucr.status(id);

-- Insert document status records
INSERT INTO docucr.status (id, name, description, type) VALUES 
('QUEUED', 'Queued', 'Document is queued for processing', 'document'),
('UPLOADING', 'Uploading', 'Document is being uploaded to storage', 'document'),
('UPLOADED', 'Uploaded', 'Document has been uploaded successfully', 'document'),
('PROCESSING', 'Processing', 'Document is being processed', 'document'),
('COMPLETED', 'Completed', 'Document processing is complete', 'document'),
('FAILED', 'Failed', 'Document processing failed', 'document')
ON CONFLICT (id) DO NOTHING;

-- Set default status for existing documents (if any)
UPDATE docucr.documents SET status_id = 'QUEUED' WHERE status_id IS NULL;

-- Make status_id NOT NULL
ALTER TABLE docucr.documents ALTER COLUMN status_id SET NOT NULL;