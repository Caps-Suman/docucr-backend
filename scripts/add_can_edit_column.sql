-- Add can_edit column to role table
ALTER TABLE docucr.role ADD COLUMN IF NOT EXISTS can_edit BOOLEAN DEFAULT TRUE;

-- Set SUPERADMIN role as non-editable
UPDATE docucr.role SET can_edit = FALSE WHERE UPPER(name) = 'SUPERADMIN';

-- Set ADMIN role as non-editable (optional)
UPDATE docucr.role SET can_edit = FALSE WHERE UPPER(name) = 'ADMIN';
