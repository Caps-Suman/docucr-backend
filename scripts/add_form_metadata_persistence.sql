-- Add new columns to documents table
ALTER TABLE docucr.documents ADD COLUMN IF NOT EXISTS document_type_id UUID;
ALTER TABLE docucr.documents ADD COLUMN IF NOT EXISTS template_id UUID;
ALTER TABLE docucr.documents ADD COLUMN IF NOT EXISTS enable_ai BOOLEAN DEFAULT FALSE;

-- Create document_form_data table
CREATE TABLE IF NOT EXISTS docucr.document_form_data (
    id SERIAL PRIMARY KEY,
    document_id INTEGER UNIQUE NOT NULL REFERENCES docucr.documents(id) ON DELETE CASCADE,
    form_id VARCHAR REFERENCES docucr.form(id) ON DELETE SET NULL,
    data JSONB,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT (now() at time zone 'utc'),
    updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT (now() at time zone 'utc')
);

-- Add foreign key constraints for document_type_id and template_id if they don't exist
DO $$ 
BEGIN 
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_documents_document_type') THEN
        ALTER TABLE docucr.documents 
        ADD CONSTRAINT fk_documents_document_type 
        FOREIGN KEY (document_type_id) REFERENCES docucr.document_types(id);
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_documents_template') THEN
        ALTER TABLE docucr.documents 
        ADD CONSTRAINT fk_documents_template 
        FOREIGN KEY (template_id) REFERENCES docucr.templates(id);
    END IF;
END $$;
