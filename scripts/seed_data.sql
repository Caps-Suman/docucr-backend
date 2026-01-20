-- Enable pgcrypto for UUID generation if not already enabled
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- 1. Clean existing data (Optional: Remove comments to enable full reset)
-- DELETE FROM docucr.user_role_module;
-- DELETE FROM docucr.role_module;
-- DELETE FROM docucr.privilege;
-- DELETE FROM docucr.module;
-- DELETE FROM docucr.user WHERE email = 'suman.singh@marvelsync.com';
-- DELETE FROM docucr.role WHERE name = 'SUPER_ADMIN';

-- 2. Create Statuses
INSERT INTO docucr.status (id, code, description, type, created_at, updated_at) VALUES
(8, 'ACTIVE', 'Active status', 'general', '2026-01-18 10:54:03.292578+00:00', '2026-01-18 10:54:03.292578+00:00'),
(9, 'INACTIVE', 'Inactive status', 'general', '2026-01-18 10:54:03.292578+00:00', '2026-01-18 10:54:03.292578+00:00'),
(10, 'QUEUED', 'Document is queued for processing', 'document', '2026-01-18 10:54:03.292578+00:00', '2026-01-18 10:54:03.292578+00:00'),
(11, 'UPLOADING', 'Document is being uploaded to storage', 'document', '2026-01-18 10:54:03.292578+00:00', '2026-01-18 10:54:03.292578+00:00'),
(12, 'UPLOADED', 'Document has been uploaded successfully', 'document', '2026-01-18 10:54:03.292578+00:00', '2026-01-18 10:54:03.292578+00:00'),
(13, 'PROCESSING', 'Document is being processed', 'document', '2026-01-18 10:54:03.292578+00:00', '2026-01-18 10:54:03.292578+00:00'),
(14, 'COMPLETED', 'Document processing is complete', 'document', '2026-01-18 10:54:03.292578+00:00', '2026-01-18 10:54:03.292578+00:00'),
(15, 'FAILED', 'Document processing failed', 'document', '2026-01-18 10:54:03.292578+00:00', '2026-01-18 10:54:03.292578+00:00'),
(16, 'AI_QUEUED', 'Document queued for AI analysis', 'document', '2026-01-18 10:54:03.292578+00:00', '2026-01-18 10:54:03.292578+00:00'),
(17, 'ANALYZING', 'Document is being analyzed by AI', 'document', '2026-01-18 10:54:03.292578+00:00', '2026-01-18 10:54:03.292578+00:00'),
(18, 'AI_FAILED', 'Document analysis by AI has failed', 'document', '2026-01-18 10:54:03.292578+00:00', '2026-01-18 10:54:03.292578+00:00'),
(19, 'UPLOAD_FAILED', 'Document upload to storage failed', 'document', '2026-01-18 10:54:03.292578+00:00', '2026-01-18 10:54:03.292578+00:00'),
(20, 'CANCELLED', 'Operation cancelled by user', 'document', '2026-01-18 10:54:03.292578+00:00', '2026-01-18 10:54:03.292578+00:00'),
(21, 'ARCHIVED', 'Document has been archived', 'document', '2026-01-18 10:54:03.292578+00:00', '2026-01-18 10:54:03.292578+00:00'),
(28, 'PENDING', 'Pending status', 'GENERAL', '2026-01-19 03:57:57.359192+00:00', NULL),
(29, 'REJECTED', 'Rejected status', 'GENERAL', '2026-01-19 03:57:57.359192+00:00', NULL)
ON CONFLICT (id) DO NOTHING;

-- 3. Create Privileges
INSERT INTO docucr.privilege (id, name, description) VALUES
(gen_random_uuid()::text, 'CREATE', 'Create new records'),
(gen_random_uuid()::text, 'READ', 'View and read records'),
(gen_random_uuid()::text, 'UPDATE', 'Edit and update records'),
(gen_random_uuid()::text, 'DELETE', 'Delete records'),
(gen_random_uuid()::text, 'EXPORT', 'Export data'),
(gen_random_uuid()::text, 'SHARE', 'Share records'),
(gen_random_uuid()::text, 'ADMIN', 'Full administrative access')
ON CONFLICT (name) DO NOTHING;

-- 4. Create Modules
INSERT INTO docucr.module (id, name, label, description, route, icon, category, display_order, color_from, color_to) VALUES
(gen_random_uuid()::text, 'dashboard', 'Dashboard', 'Main dashboard with overview and analytics', '/dashboard', 'LayoutDashboard', 'main', 1, '#667eea', '#764ba2'),
(gen_random_uuid()::text, 'documents', 'Documents', 'Document management and processing', '/documents', 'FileText', 'main', 2, '#f093fb', '#f5576c'),
(gen_random_uuid()::text, 'templates', 'Templates', 'Document templates and forms', '/templates', 'Layout', 'main', 3, '#4facfe', '#00f2fe'),
(gen_random_uuid()::text, 'sops', 'SOPs', 'Standard Operating Procedures', '/sops', 'BookOpen', 'main', 4, '#43e97b', '#38f9d7'),
(gen_random_uuid()::text, 'clients', 'Clients', 'Client management and information', '/clients', 'Users', 'main', 5, '#fa709a', '#fee140'),
(gen_random_uuid()::text, 'users_permissions', 'User & Permissions', 'User management and access control', '/users-permissions', 'Shield', 'admin', 6, '#a8edea', '#fed6e3'),
(gen_random_uuid()::text, 'settings', 'Settings', 'System configuration and preferences', '/settings', 'Settings', 'admin', 7, '#d299c2', '#fef9d7'),
(gen_random_uuid()::text, 'profile', 'Profile', 'User profile and account settings', '/profile', 'User', 'user', 8, '#89f7fe', '#66a6ff')
ON CONFLICT (name) DO NOTHING;

-- 5. Create SUPER_ADMIN Role
INSERT INTO docucr.role (id, name, description, is_active) VALUES
(gen_random_uuid()::text, 'SUPER_ADMIN', 'Super Administrator with full access', true)
ON CONFLICT (name) DO NOTHING;

-- 6. Create Super Admin User
INSERT INTO docucr.user (id, email, username, hashed_password, first_name, last_name, is_active, is_superuser, is_client) VALUES
(
    gen_random_uuid()::text, 
    'suman.singh@marvelsync.com', 
    'suman.singh', 
    '$2b$12$9mQJRO5BTRdk320ga1uhBOD1YPpYeerKmhm4LSupus2M1GKkYgqv6', -- Suman@docucr22
    'Suman', 
    'Singh', 
    true, 
    true, 
    false
)
ON CONFLICT (email) DO NOTHING;

-- 7. Assign All Privileges for All Modules to SUPER_ADMIN Role (populating role_module)
INSERT INTO docucr.role_module (id, role_id, module_id, privilege_id)
SELECT 
    gen_random_uuid()::text,
    r.id, 
    m.id, 
    p.id
FROM 
    docucr.role r,
    docucr.module m,
    docucr.privilege p
WHERE 
    r.name = 'SUPER_ADMIN'
    AND NOT EXISTS (
        SELECT 1 FROM docucr.role_module rm 
        WHERE rm.role_id = r.id AND rm.module_id = m.id AND rm.privilege_id = p.id
    );

-- 8. Grant SUPER_ADMIN Role Access to User (populating user_role_module)
-- This links the specific role_module entries to the user
INSERT INTO docucr.user_role_module (id, user_id, role_module_id)
SELECT 
    gen_random_uuid()::text,
    u.id,
    rm.id
FROM 
    docucr.user u,
    docucr.role_module rm
JOIN 
    docucr.role r ON rm.role_id = r.id
WHERE 
    u.email = 'suman.singh@marvelsync.com' 
    AND r.name = 'SUPER_ADMIN'
    AND NOT EXISTS (
        SELECT 1 FROM docucr.user_role_module urm 
        WHERE urm.user_id = u.id AND urm.role_module_id = rm.id
    );

-- Output confirmation
DO $$
DECLARE
    user_count INTEGER;
    priv_count INTEGER;
    module_count INTEGER;
    rm_count INTEGER;
BEGIN
    SELECT count(*) INTO user_count FROM docucr.user WHERE email = 'suman.singh@marvelsync.com';
    SELECT count(*) INTO priv_count FROM docucr.privilege;
    SELECT count(*) INTO module_count FROM docucr.module;
    SELECT count(*) INTO rm_count FROM docucr.user_role_module urm JOIN docucr.user u ON urm.user_id = u.id WHERE u.email = 'suman.singh@marvelsync.com';
    
    RAISE NOTICE 'Seed Complete: User Suman(%), Privileges(%), Modules(%), Assigned Permissions(%)', 
        user_count, priv_count, module_count, rm_count;
END $$;
