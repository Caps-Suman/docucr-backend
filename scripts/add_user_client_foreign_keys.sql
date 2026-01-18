-- Add foreign key columns for direct user-client relationships

-- Add client_id to user table
ALTER TABLE docucr.user ADD COLUMN client_id UUID REFERENCES docucr.client(id);

-- Add user_id to client table  
ALTER TABLE docucr.client ADD COLUMN user_id VARCHAR REFERENCES docucr.user(id);

-- Create indexes for performance
CREATE INDEX idx_user_client_id ON docucr.user(client_id);
CREATE INDEX idx_client_user_id ON docucr.client(user_id);