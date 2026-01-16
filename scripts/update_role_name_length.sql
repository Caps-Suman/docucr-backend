-- Migration to update role name column to enforce 50 character limit
-- Run this script to update the existing database schema

-- Update the role table to set the name column to VARCHAR(50)
ALTER TABLE docucr.role 
ALTER COLUMN name TYPE VARCHAR(50);

-- Verify the change
SELECT column_name, data_type, character_maximum_length 
FROM information_schema.columns 
WHERE table_schema = 'docucr' 
AND table_name = 'role' 
AND column_name = 'name';
