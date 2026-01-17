-- Create document_types table
CREATE TABLE IF NOT EXISTS docucr.document_types (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(100) NOT NULL UNIQUE,
    description TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create templates table
CREATE TABLE IF NOT EXISTS docucr.templates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    template_name VARCHAR(100) NOT NULL,
    description TEXT,
    document_type_id UUID NOT NULL REFERENCES docucr.document_types(id) ON DELETE CASCADE,
    extraction_fields JSONB DEFAULT '[]'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_document_types_name ON docucr.document_types(name);
CREATE INDEX IF NOT EXISTS idx_templates_document_type_id ON docucr.templates(document_type_id);
CREATE INDEX IF NOT EXISTS idx_templates_name ON docucr.templates(template_name);

-- Apply triggers (reuse existing function)
CREATE TRIGGER update_document_types_updated_at 
    BEFORE UPDATE ON docucr.document_types 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_templates_updated_at 
    BEFORE UPDATE ON docucr.templates 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Insert some sample document types
INSERT INTO docucr.document_types (name, description) VALUES 
    ('Invoice', 'Commercial invoices and billing documents'),
    ('Contract', 'Legal contracts and agreements'),
    ('ID Proof', 'Identity verification documents'),
    ('Receipt', 'Purchase receipts and transaction records')
ON CONFLICT (name) DO NOTHING;