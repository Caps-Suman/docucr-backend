-- Create docucr schema in RDS
CREATE SCHEMA IF NOT EXISTS docucr;

-- Grant privileges to the user
GRANT ALL PRIVILEGES ON SCHEMA docucr TO ivrocrstaging;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA docucr TO ivrocrstaging;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA docucr TO ivrocrstaging;

-- Set default privileges for future objects
ALTER DEFAULT PRIVILEGES IN SCHEMA docucr GRANT ALL ON TABLES TO ivrocrstaging;
ALTER DEFAULT PRIVILEGES IN SCHEMA docucr GRANT ALL ON SEQUENCES TO ivrocrstaging;

-- Verify schema creation
SELECT schema_name FROM information_schema.schemata WHERE schema_name = 'docucr';
