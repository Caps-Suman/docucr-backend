-- Comprehensive Master Data SQL Export
-- All human-readable IDs migrated to UUIDs (except where Integers are required).
-- Full coverage of baseline models.

-- Set search path
SET search_path TO docucr, public;

-- 1. Statuses (Integers)
INSERT INTO status (id, code, description, type) VALUES
(1, 'ACTIVE', 'Item is active', 'general'),
(2, 'INACTIVE', 'Item is inactive', 'general'),
(3, 'PENDING', 'Item is pending action', 'general'),
(4, 'REJECTED', 'Item was rejected', 'general'),
(5, 'UPLOADED', 'File has been uploaded', 'document'),
(6, 'QUEUED', 'Document is queued for processing', 'document'),
(7, 'PROCESSING', 'Document is currently being processed', 'document'),
(8, 'COMPLETED', 'Processing is complete', 'document'),
(9, 'FAILED', 'Processing failed', 'document'),
(10, 'ARCHIVED', 'Item has been archived', 'general'),
(11, 'CANCELLED', 'Operation was cancelled', 'general'),
(12, 'UPLOAD_FAILED', 'Failed to upload to storage', 'document')
ON CONFLICT (code) DO UPDATE SET 
    description = EXCLUDED.description,
    type = EXCLUDED.type;

-- 2. Privileges
INSERT INTO privilege (id, name, description) VALUES
('9a147d3b-81c2-4b5a-a1e6-44401bf3062f', 'CREATE', 'Create new records'),
('50a19031-a670-417e-9dd5-13d1abdbee6d', 'READ', 'View and read records'),
('f95fa0f7-19b1-4a0f-9747-28dcca144d4a', 'UPDATE', 'Edit and update records'),
('68b85749-83c1-4e05-8ec4-a3e7a7fc5d3a', 'DELETE', 'Delete records'),
('67d65b63-bb50-4627-990d-6dfbeb7da44b', 'EXPORT', 'Export data'),
('eb43c11d-f88a-44f3-8a46-c5008f500a64', 'IMPORT', 'Import data'),
('601cb59a-7443-4faa-b377-d53ca2d3c9fe', 'APPROVE', 'Approve workflows'),
('d0ee2d09-1772-4961-a7fb-22e2d4508bc8', 'ADMIN', 'Full management access')
ON CONFLICT (name) DO UPDATE SET 
    description = EXCLUDED.description;

-- 3. Modules
INSERT INTO module (id, name, label, description, route, icon, category, display_order, is_active) VALUES
('81a2f87b-8483-4191-97a6-1f3a86b8ba8e', 'dashboard', 'Dashboard', 'Main dashboard with overview and analytics', '/dashboard', 'LayoutDashboard', 'main', 1, TRUE),
('75e47454-e0c0-4e52-8eb2-f7c23446c4fd', 'documents', 'Documents', 'Document management and processing', '/documents', 'FileText', 'main', 2, TRUE),
('921a8dff-14ee-42bd-822f-28c03f32ae1a', 'templates', 'Templates', 'Document templates and forms', '/templates', 'Layout', 'main', 3, TRUE),
('61a6aeef-2378-4dae-81b6-eafba87a519a', 'sops', 'SOPs', 'Standard Operating Procedures', '/sops', 'BookOpen', 'main', 4, TRUE),
('bdfac474-42ac-4233-b24b-cb167b7b034d', 'clients', 'Clients', 'Client management and information', '/clients', 'Users', 'main', 5, TRUE),
('e518f0aa-d987-4d14-b8cc-a5abc1daeac5', 'users_permissions', 'User & Permissions', 'User management and access control', '/users-permissions', 'Shield', 'admin', 6, TRUE),
('15baf30a-7ab7-4997-8086-dce65da5cac2', 'settings', 'Settings', 'System configuration and preferences', '/settings', 'Settings', 'admin', 7, TRUE),
('ff2ed097-c906-4f5d-a9f0-c17a334bb7ef', 'profile', 'Profile', 'User profile and account settings', '/profile', 'User', 'user', 8, TRUE),
('e3f272ce-15d4-4cce-80e4-7d270e286336', 'form_management', 'Form Management', 'Create and manage dynamic forms', '/forms', 'FileEdit', 'admin', 9, TRUE),
('a9d7e3c1-5b7f-4f7d-8e5a-1c7a334bb7ef', 'activity_log', 'Activity Logs', 'View system activity logs', '/activity-logs', 'Activity', 'admin', 10, TRUE)
ON CONFLICT (name) DO UPDATE SET 
    label = EXCLUDED.label,
    description = EXCLUDED.description,
    route = EXCLUDED.route,
    icon = EXCLUDED.icon,
    category = EXCLUDED.category,
    display_order = EXCLUDED.display_order;

-- 4. Submodules
INSERT INTO submodule (id, module_id, name, label, route_key, display_order) VALUES
('038662ed-66e6-486a-b7ae-ee1b39abeb7a', 'e518f0aa-d987-4d14-b8cc-a5abc1daeac5', 'user_module', 'Users', 'user_management', 1),
('bf3b5607-1646-45a7-9dae-02f06ae31957', 'e518f0aa-d987-4d14-b8cc-a5abc1daeac5', 'role_module', 'Roles', 'role_management', 2),
('4884d64e-1dbf-4308-a12d-de5bfc008d0d', '921a8dff-14ee-42bd-822f-28c03f32ae1a', 'document_types', 'Document Types', 'document_types', 1),
('ea8ca942-6d2e-444f-9325-92c0ae05c5e1', '921a8dff-14ee-42bd-822f-28c03f32ae1a', 'templates_list', 'Templates List', 'templates_list', 2),
('a3a1862c-d75b-4d4b-8fed-da8293c8a64b', '15baf30a-7ab7-4997-8086-dce65da5cac2', 'document_list_view_config', 'Document List Config', 'document_list_view_config', 1),
('a65bbac9-2431-41b7-bdb3-b4669ccf6506', '15baf30a-7ab7-4997-8086-dce65da5cac2', 'webhook_management', 'Webhook Management', 'webhook_management', 2)
ON CONFLICT (id) DO UPDATE SET 
    label = EXCLUDED.label,
    route_key = EXCLUDED.route_key,
    display_order = EXCLUDED.display_order;

-- 5. Roles
INSERT INTO role (id, name, description, status_id, can_edit, is_default) VALUES
('5b0660b7-f68c-4655-8510-7dee8540781d', 'SUPER_ADMIN', 'System administrator with full access', 1, FALSE, TRUE),
('52d854f8-09a4-49c6-817e-5e4e2783e06d', 'ORGANISATION_ADMIN', 'Organisation level administrator', 1, TRUE, TRUE),
('d875f220-5e8f-47d8-9f1a-3d7a88bb7e39', 'ADMIN', 'Standard administrator', 1, TRUE, FALSE),
('4646b137-fe4e-4552-9904-002a6325bfbb', 'USER', 'Regular system user', 1, TRUE, FALSE)
ON CONFLICT (name) DO UPDATE SET 
    description = EXCLUDED.description,
    status_id = EXCLUDED.status_id,
    can_edit = EXCLUDED.can_edit,
    is_default = EXCLUDED.is_default;

-- 6. Organisation (Marvelsync)
INSERT INTO organisation (id, name, email, username, hashed_password, status_id) VALUES
('235660d2-2d3f-432b-9573-9ee8aedcc25e', 'Marvelsync', 'akanksha.jha@marvelsync.com', 'marvelsync', '$2b$12$/z5GlfSUpKYRG1pcemwR9uaBjWYv/hOG0fOFSfZ6LTpkeKapKkUhW', 1)
ON CONFLICT (email) DO NOTHING;

-- 7. Specific User (suman.singh@marvelsync.com)
INSERT INTO "user" (id, email, username, hashed_password, first_name, last_name, is_superuser, status_id, organisation_id) VALUES
('56354a92-77e0-4ca2-bc2d-16f61427fa3b', 'suman.singh@marvelsync.com', 'sumansingh', '$2b$12$/z5GlfSUpKYRG1pcemwR9uaBjWYv/hOG0fOFSfZ6LTpkeKapKkUhW', 'Suman', 'Singh', TRUE, 1, NULL)
ON CONFLICT (email) DO UPDATE SET 
    is_superuser = TRUE,
    status_id = 1,
    organisation_id = NULL;

-- 8. User-Role Mapping
INSERT INTO user_role (id, user_id, role_id) VALUES
('2b91ad53-50b8-48b4-baf7-51ef327f2271', '56354a92-77e0-4ca2-bc2d-16f61427fa3b', '5b0660b7-f68c-4655-8510-7dee8540781d')
ON CONFLICT (id) DO NOTHING;

-- 10. Document Types
INSERT INTO document_types (id, name, description, status_id, organisation_id) VALUES
('15dd069f-0d08-44e5-8fdf-7defb0ddc550', 'SOP', 'Standard Operating Procedure', 1, '235660d2-2d3f-432b-9573-9ee8aedcc25e'),
('f085a1ff-b62b-4316-bdfc-5acb8acb6820', 'ADMISSION_FORM', 'Client admission form', 1, '235660d2-2d3f-432b-9573-9ee8aedcc25e')
ON CONFLICT (name, organisation_id) DO NOTHING;

-- 11. Role-Module Permissions (Grant everything to SUPER_ADMIN)
DO $$
DECLARE
    module_rec RECORD;
    priv_rec RECORD;
    role_id UUID := '5b0660b7-f68c-4655-8510-7dee8540781d';
BEGIN
    FOR module_rec IN SELECT id FROM docucr.module LOOP
        FOR priv_rec IN SELECT id FROM docucr.privilege LOOP
            INSERT INTO docucr.role_module (id, role_id, module_id, privilege_id)
            VALUES (gen_random_uuid(), role_id, module_rec.id, priv_rec.id)
            ON CONFLICT DO NOTHING;
        END LOOP;
    END LOOP;
END $$;

-- 12. Role-Submodule Permissions (Grant everything to SUPER_ADMIN)
DO $$
DECLARE
    submodule_rec RECORD;
    priv_rec RECORD;
    role_id UUID := '5b0660b7-f68c-4655-8510-7dee8540781d';
BEGIN
    FOR submodule_rec IN SELECT id FROM docucr.submodule LOOP
        FOR priv_rec IN SELECT id FROM docucr.privilege LOOP
            INSERT INTO docucr.role_submodule (id, role_id, submodule_id, privilege_id)
            VALUES (gen_random_uuid(), role_id, submodule_rec.id, priv_rec.id)
            ON CONFLICT DO NOTHING;
        END LOOP;
    END LOOP;
END $$;

-- 13. Additional Baseline Tables

-- Form Models
INSERT INTO form (id, name, description, status_id, organisation_id) VALUES
('b405d9ef-adf5-4fdc-86ed-7576281647f8', 'Default Intake Form', 'Standard intake questionnaire', 1, '235660d2-2d3f-432b-9573-9ee8aedcc25e')
ON CONFLICT (id) DO NOTHING;

-- Printer
INSERT INTO printer (id, name, ip_address, port, protocol, status) VALUES
('35d499a0-12f4-456d-a088-1af147a1ad65', 'Office LaserJet', '192.168.1.100', 9100, 'RAW', 'ACTIVE')
ON CONFLICT (id) DO NOTHING;

-- Webhook
INSERT INTO webhook (id, user_id, name, url, events, is_active) VALUES
('b22d229c-1b66-483e-bc01-cba2f68141bb', '56354a92-77e0-4ca2-bc2d-16f61427fa3b', 'Local Dev Hook', 'http://localhost:3000/webhook', '["document.completed"]', TRUE)
ON CONFLICT (id) DO NOTHING;

-- SOP
INSERT INTO sop (id, title, category, provider_type, status_id, organisation_id) VALUES
('8714d6b1-a852-43b4-8551-c43208c643da', 'HIPAA Compliance Guide', 'legal', 'ALL', 1, '235660d2-2d3f-432b-9573-9ee8aedcc25e')
ON CONFLICT (id) DO NOTHING;
