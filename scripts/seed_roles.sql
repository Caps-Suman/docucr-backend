-- Seed additional roles for hierarchy
-- This script should be run after the main seed_data.sql

-- Create additional roles for hierarchy
INSERT INTO docucr.role (id, name, description, status_id, can_edit, created_at, updated_at) VALUES
(gen_random_uuid()::text, 'ADMIN', 'Administrator with access to most features', 8, true, NOW(), NOW()),
(gen_random_uuid()::text, 'SUPERVISOR', 'Supervisor who can manage their team', 8, true, NOW(), NOW()),
(gen_random_uuid()::text, 'USER', 'Regular user with basic access', 8, true, NOW(), NOW())
ON CONFLICT (name) DO NOTHING;

-- Output confirmation
DO $$
DECLARE
    admin_role_id TEXT;
    supervisor_role_id TEXT;
    user_role_id TEXT;
BEGIN
    SELECT id INTO admin_role_id FROM docucr.role WHERE name = 'ADMIN';
    SELECT id INTO supervisor_role_id FROM docucr.role WHERE name = 'SUPERVISOR';
    SELECT id INTO user_role_id FROM docucr.role WHERE name = 'USER';
    
    RAISE NOTICE 'Roles seeded: ADMIN(%), SUPERVISOR(%), USER(%)', 
        admin_role_id, supervisor_role_id, user_role_id;
END $$;
