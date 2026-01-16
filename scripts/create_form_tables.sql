-- Create form table
CREATE TABLE IF NOT EXISTS docucr.form (
    id VARCHAR(36) PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    status_id VARCHAR(36) REFERENCES docucr.status(id),
    created_by VARCHAR(36) NOT NULL REFERENCES docucr.user(id),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX idx_form_name ON docucr.form(name);
CREATE INDEX idx_form_status ON docucr.form(status_id);

-- Create form_field table
CREATE TABLE IF NOT EXISTS docucr.form_field (
    id VARCHAR(36) PRIMARY KEY,
    form_id VARCHAR(36) NOT NULL REFERENCES docucr.form(id) ON DELETE CASCADE,
    field_type VARCHAR(50) NOT NULL,
    label VARCHAR(200) NOT NULL,
    placeholder VARCHAR(200),
    required BOOLEAN DEFAULT FALSE,
    options JSONB,
    validation JSONB,
    "order" INTEGER NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_form_field_form_id ON docucr.form_field(form_id);
CREATE INDEX idx_form_field_order ON docucr.form_field(form_id, "order");
