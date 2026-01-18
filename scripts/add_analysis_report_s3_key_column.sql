-- Add analysis_report_s3_key column to documents table
ALTER TABLE docucr.documents 
ADD COLUMN IF NOT EXISTS analysis_report_s3_key VARCHAR(500);