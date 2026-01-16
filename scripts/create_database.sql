-- Create docucr database
CREATE DATABASE docucr_db;

-- Connect to the new database and create schema
\c docucr_db

CREATE SCHEMA IF NOT EXISTS docucr;

-- Grant privileges
GRANT ALL PRIVILEGES ON DATABASE docucr_db TO ivrocrstaging;
GRANT ALL PRIVILEGES ON SCHEMA docucr TO ivrocrstaging;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA docucr TO ivrocrstaging;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA docucr TO ivrocrstaging;

-- Set default privileges
ALTER DEFAULT PRIVILEGES IN SCHEMA docucr GRANT ALL ON TABLES TO ivrocrstaging;
ALTER DEFAULT PRIVILEGES IN SCHEMA docucr GRANT ALL ON SEQUENCES TO ivrocrstaging;
