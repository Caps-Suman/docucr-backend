-- Add is_system column to form_field table
ALTER TABLE docucr.form_field 
ADD COLUMN is_system BOOLEAN DEFAULT FALSE;

-- Update existing records to set is_system = false (default)
UPDATE docucr.form_field 
SET is_system = FALSE 
WHERE is_system IS NULL;