CREATE SCHEMA IF NOT EXISTS docucr;
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE docucr.client (
	id UUID NOT NULL, 
	business_name VARCHAR(255), 
	first_name VARCHAR(100), 
	middle_name VARCHAR(100), 
	last_name VARCHAR(100), 
	npi VARCHAR(10), 
	type VARCHAR(50), 
	address_line_1 VARCHAR(250), 
	address_line_2 VARCHAR(250), 
	city VARCHAR(250), 
	state_code VARCHAR(2), 
	state_name VARCHAR(50), 
	country VARCHAR(50), 
	zip_code VARCHAR(10), 
	is_user BOOLEAN, 
	created_by VARCHAR, 
	status_id INTEGER, 
	organisation_id VARCHAR, 
	description TEXT, 
	deleted_at TIMESTAMP WITH TIME ZONE, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now(), 
	updated_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_client_zip_9_digit CHECK (zip_code ~ '^[0-9]{5}-[0-9]{4}$'), 
	CONSTRAINT ck_client_state_code_len CHECK (char_length(state_code) = 2), 
	FOREIGN KEY(status_id) REFERENCES docucr.status (id)
);

CREATE TABLE docucr.module (
	id VARCHAR NOT NULL, 
	name VARCHAR NOT NULL, 
	label VARCHAR NOT NULL, 
	description TEXT, 
	route VARCHAR NOT NULL, 
	icon VARCHAR, 
	category VARCHAR NOT NULL, 
	has_submodules BOOLEAN, 
	submodules JSON, 
	is_active BOOLEAN, 
	display_order INTEGER, 
	color_from VARCHAR, 
	color_to VARCHAR, 
	color_shadow VARCHAR, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now(), 
	updated_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id)
);

CREATE TABLE docucr.organisation (
	id VARCHAR NOT NULL, 
	name VARCHAR NOT NULL, 
	email VARCHAR NOT NULL, 
	username VARCHAR NOT NULL, 
	hashed_password VARCHAR NOT NULL, 
	first_name VARCHAR, 
	middle_name VARCHAR, 
	last_name VARCHAR, 
	phone_country_code VARCHAR(5), 
	phone_number VARCHAR(15), 
	status_id INTEGER, 
	is_superuser BOOLEAN, 
	is_client BOOLEAN, 
	is_supervisor BOOLEAN, 
	client_id UUID, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now(), 
	updated_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(status_id) REFERENCES docucr.status (id)
);

CREATE TABLE docucr.otp (
	id VARCHAR NOT NULL, 
	email VARCHAR NOT NULL, 
	otp_code VARCHAR NOT NULL, 
	purpose VARCHAR NOT NULL, 
	is_used BOOLEAN, 
	expires_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now(), 
	PRIMARY KEY (id)
);

CREATE TABLE docucr.printer (
	id VARCHAR NOT NULL, 
	name VARCHAR NOT NULL, 
	ip_address VARCHAR NOT NULL, 
	port INTEGER NOT NULL, 
	protocol VARCHAR NOT NULL, 
	description VARCHAR, 
	status VARCHAR, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now(), 
	updated_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id)
);

CREATE TABLE docucr.privilege (
	id VARCHAR NOT NULL, 
	name VARCHAR NOT NULL, 
	description TEXT, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now(), 
	updated_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id)
);

CREATE TABLE docucr.provider (
	id UUID NOT NULL, 
	created_by VARCHAR, 
	first_name VARCHAR NOT NULL, 
	middle_name VARCHAR, 
	last_name VARCHAR, 
	npi VARCHAR, 
	address_line_1 VARCHAR(250), 
	address_line_2 VARCHAR(250), 
	city VARCHAR(250), 
	state_code VARCHAR(2), 
	state_name VARCHAR(50), 
	country VARCHAR(50), 
	zip_code VARCHAR(10), 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_client_zip_9_digit CHECK (zip_code ~ '^[0-9]{5}-[0-9]{4}$'), 
	CONSTRAINT ck_client_state_code_len CHECK (char_length(state_code) = 2)
);

CREATE TABLE docucr.status (
	id SERIAL NOT NULL, 
	code VARCHAR NOT NULL, 
	description TEXT, 
	type VARCHAR, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now(), 
	updated_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id)
);

CREATE TABLE docucr."user" (
	id VARCHAR NOT NULL, 
	email VARCHAR NOT NULL, 
	username VARCHAR NOT NULL, 
	hashed_password VARCHAR NOT NULL, 
	first_name VARCHAR, 
	middle_name VARCHAR, 
	last_name VARCHAR, 
	phone_country_code VARCHAR(5), 
	phone_number VARCHAR(15), 
	is_superuser BOOLEAN, 
	is_supervisor BOOLEAN, 
	is_client BOOLEAN, 
	client_id UUID, 
	status_id INTEGER, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now(), 
	updated_at TIMESTAMP WITH TIME ZONE, 
	created_by VARCHAR, 
	organisation_id VARCHAR, 
	profile_image_url VARCHAR, 
	PRIMARY KEY (id), 
	FOREIGN KEY(status_id) REFERENCES docucr.status (id)
);

CREATE TABLE docucr.activity_log (
	id UUID DEFAULT gen_random_uuid() NOT NULL, 
	user_id VARCHAR, 
	organisation_id VARCHAR, 
	action VARCHAR NOT NULL, 
	entity_type VARCHAR NOT NULL, 
	entity_id VARCHAR, 
	details JSON, 
	ip_address VARCHAR, 
	user_agent TEXT, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now(), 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES docucr."user" (id), 
	FOREIGN KEY(organisation_id) REFERENCES docucr.organisation (id)
);

CREATE TABLE docucr.document_list_configs (
	id SERIAL NOT NULL, 
	user_id VARCHAR, 
	organisation_id VARCHAR, 
	configuration JSONB NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES docucr."user" (id), 
	FOREIGN KEY(organisation_id) REFERENCES docucr.organisation (id)
);

CREATE TABLE docucr.document_types (
	id UUID NOT NULL, 
	name VARCHAR(100) NOT NULL, 
	description TEXT, 
	status_id INTEGER NOT NULL, 
	organisation_id VARCHAR, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now(), 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now(), 
	PRIMARY KEY (id), 
	FOREIGN KEY(status_id) REFERENCES docucr.status (id), 
	FOREIGN KEY(organisation_id) REFERENCES docucr.organisation (id)
);

CREATE TABLE docucr.form (
	id VARCHAR NOT NULL, 
	name VARCHAR(100) NOT NULL, 
	description TEXT, 
	status_id INTEGER, 
	created_by VARCHAR, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now(), 
	updated_at TIMESTAMP WITH TIME ZONE, 
	organisation_id VARCHAR, 
	PRIMARY KEY (id), 
	FOREIGN KEY(status_id) REFERENCES docucr.status (id), 
	FOREIGN KEY(organisation_id) REFERENCES docucr.organisation (id)
);

CREATE TABLE docucr.role (
	id VARCHAR NOT NULL, 
	name VARCHAR(50) NOT NULL, 
	description TEXT, 
	is_default BOOLEAN, 
	status_id INTEGER, 
	can_edit BOOLEAN, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now(), 
	updated_at TIMESTAMP WITH TIME ZONE, 
	created_by VARCHAR, 
	organisation_id VARCHAR, 
	PRIMARY KEY (id), 
	CONSTRAINT ux_role_name_org UNIQUE (name, organisation_id), 
	FOREIGN KEY(status_id) REFERENCES docucr.status (id), 
	FOREIGN KEY(created_by) REFERENCES docucr."user" (id), 
	FOREIGN KEY(organisation_id) REFERENCES docucr.organisation (id)
);

CREATE TABLE docucr.sop (
	id UUID NOT NULL, 
	title VARCHAR NOT NULL, 
	category VARCHAR NOT NULL, 
	provider_type VARCHAR NOT NULL, 
	client_id UUID, 
	provider_info JSONB, 
	workflow_process JSONB, 
	billing_guidelines JSONB, 
	payer_guidelines JSONB, 
	coding_rules JSONB, 
	coding_rules_cpt JSONB, 
	coding_rules_icd JSONB, 
	status_id INTEGER, 
	workflow_status_id INTEGER, 
	created_by VARCHAR, 
	organisation_id VARCHAR, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now(), 
	updated_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(client_id) REFERENCES docucr.client (id), 
	FOREIGN KEY(status_id) REFERENCES docucr.status (id), 
	FOREIGN KEY(workflow_status_id) REFERENCES docucr.status (id), 
	FOREIGN KEY(created_by) REFERENCES docucr."user" (id), 
	FOREIGN KEY(organisation_id) REFERENCES docucr.organisation (id)
);

CREATE TABLE docucr.submodule (
	id VARCHAR NOT NULL, 
	module_id VARCHAR NOT NULL, 
	name VARCHAR NOT NULL, 
	label VARCHAR NOT NULL, 
	route_key VARCHAR NOT NULL, 
	display_order INTEGER, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now(), 
	updated_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(module_id) REFERENCES docucr.module (id)
);

CREATE TABLE docucr.user_client (
	id VARCHAR NOT NULL, 
	user_id VARCHAR NOT NULL, 
	client_id UUID NOT NULL, 
	assigned_by VARCHAR, 
	organisation_id VARCHAR, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now(), 
	PRIMARY KEY (id), 
	CONSTRAINT uq_user_client UNIQUE (user_id, client_id), 
	FOREIGN KEY(user_id) REFERENCES docucr."user" (id), 
	FOREIGN KEY(client_id) REFERENCES docucr.client (id), 
	FOREIGN KEY(assigned_by) REFERENCES docucr."user" (id), 
	FOREIGN KEY(organisation_id) REFERENCES docucr.organisation (id)
);

CREATE TABLE docucr.user_supervisor (
	id VARCHAR NOT NULL, 
	user_id VARCHAR NOT NULL, 
	supervisor_id VARCHAR NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now(), 
	updated_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES docucr."user" (id), 
	FOREIGN KEY(supervisor_id) REFERENCES docucr."user" (id)
);

CREATE TABLE docucr.webhook (
	id VARCHAR NOT NULL, 
	user_id VARCHAR NOT NULL, 
	name VARCHAR(100) NOT NULL, 
	url VARCHAR(500) NOT NULL, 
	secret VARCHAR(255), 
	events JSON NOT NULL, 
	is_active BOOLEAN, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now(), 
	updated_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES docucr."user" (id)
);

CREATE TABLE docucr.form_field (
	id VARCHAR NOT NULL, 
	form_id VARCHAR NOT NULL, 
	field_type VARCHAR(50) NOT NULL, 
	label VARCHAR(200) NOT NULL, 
	placeholder VARCHAR(200), 
	required BOOLEAN, 
	default_value JSON, 
	options JSON, 
	validation JSON, 
	"order" INTEGER NOT NULL, 
	is_system BOOLEAN, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now(), 
	PRIMARY KEY (id), 
	FOREIGN KEY(form_id) REFERENCES docucr.form (id) ON DELETE CASCADE
);

CREATE TABLE docucr.organisation_role (
	id VARCHAR NOT NULL, 
	organisation_id VARCHAR NOT NULL, 
	role_id VARCHAR NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now(), 
	updated_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(organisation_id) REFERENCES docucr.organisation (id), 
	FOREIGN KEY(role_id) REFERENCES docucr.role (id)
);

CREATE TABLE docucr.role_module (
	id VARCHAR NOT NULL, 
	role_id VARCHAR NOT NULL, 
	module_id VARCHAR NOT NULL, 
	privilege_id VARCHAR NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now(), 
	updated_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(role_id) REFERENCES docucr.role (id), 
	FOREIGN KEY(module_id) REFERENCES docucr.module (id), 
	FOREIGN KEY(privilege_id) REFERENCES docucr.privilege (id)
);

CREATE TABLE docucr.role_submodule (
	id VARCHAR NOT NULL, 
	role_id VARCHAR NOT NULL, 
	submodule_id VARCHAR NOT NULL, 
	privilege_id VARCHAR NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now(), 
	updated_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(role_id) REFERENCES docucr.role (id), 
	FOREIGN KEY(submodule_id) REFERENCES docucr.submodule (id), 
	FOREIGN KEY(privilege_id) REFERENCES docucr.privilege (id)
);

CREATE TABLE docucr.sop_provider_mapping (
	id UUID NOT NULL, 
	sop_id UUID NOT NULL, 
	provider_id UUID NOT NULL, 
	created_by VARCHAR, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now(), 
	PRIMARY KEY (id), 
	FOREIGN KEY(sop_id) REFERENCES docucr.sop (id), 
	FOREIGN KEY(provider_id) REFERENCES docucr.provider (id)
);

CREATE TABLE docucr.templates (
	id UUID NOT NULL, 
	template_name VARCHAR(100) NOT NULL, 
	description TEXT, 
	document_type_id UUID NOT NULL, 
	status_id INTEGER NOT NULL, 
	extraction_fields JSON DEFAULT '[]'::json NOT NULL, 
	created_by VARCHAR, 
	organisation_id VARCHAR, 
	updated_by VARCHAR, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (template_name, document_type_id), 
	FOREIGN KEY(document_type_id) REFERENCES docucr.document_types (id), 
	FOREIGN KEY(status_id) REFERENCES docucr.status (id), 
	FOREIGN KEY(created_by) REFERENCES docucr."user" (id), 
	FOREIGN KEY(organisation_id) REFERENCES docucr.organisation (id), 
	FOREIGN KEY(updated_by) REFERENCES docucr."user" (id)
);

CREATE TABLE docucr.user_role (
	id VARCHAR NOT NULL, 
	user_id VARCHAR NOT NULL, 
	role_id VARCHAR NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now(), 
	updated_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES docucr."user" (id), 
	FOREIGN KEY(role_id) REFERENCES docucr.role (id)
);

CREATE TABLE docucr.documents (
	id SERIAL NOT NULL, 
	filename VARCHAR(255) NOT NULL, 
	original_filename VARCHAR(255) NOT NULL, 
	file_size INTEGER NOT NULL, 
	content_type VARCHAR(100) NOT NULL, 
	s3_key VARCHAR(500), 
	s3_bucket VARCHAR(100), 
	status_id INTEGER NOT NULL, 
	upload_progress INTEGER, 
	error_message TEXT, 
	analysis_report_s3_key VARCHAR(500), 
	is_archived BOOLEAN NOT NULL, 
	total_pages INTEGER, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	organisation_id VARCHAR NOT NULL, 
	created_by VARCHAR NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	document_type_id UUID, 
	template_id UUID, 
	client_id UUID, 
	enable_ai BOOLEAN NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(status_id) REFERENCES docucr.status (id), 
	FOREIGN KEY(organisation_id) REFERENCES docucr.organisation (id), 
	FOREIGN KEY(created_by) REFERENCES docucr."user" (id), 
	FOREIGN KEY(document_type_id) REFERENCES docucr.document_types (id), 
	FOREIGN KEY(template_id) REFERENCES docucr.templates (id), 
	FOREIGN KEY(client_id) REFERENCES docucr.client (id)
);

CREATE TABLE docucr.user_role_module (
	id VARCHAR NOT NULL, 
	user_id VARCHAR NOT NULL, 
	role_module_id VARCHAR NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now(), 
	updated_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES docucr."user" (id), 
	FOREIGN KEY(role_module_id) REFERENCES docucr.role_module (id)
);

CREATE TABLE docucr.document_form_data (
	id SERIAL NOT NULL, 
	document_id INTEGER NOT NULL, 
	form_id VARCHAR, 
	data JSONB, 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	updated_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id), 
	UNIQUE (document_id), 
	FOREIGN KEY(document_id) REFERENCES docucr.documents (id), 
	FOREIGN KEY(form_id) REFERENCES docucr.form (id)
);

CREATE TABLE docucr.document_shares (
	id UUID NOT NULL, 
	document_id INTEGER NOT NULL, 
	user_id VARCHAR NOT NULL, 
	shared_by_user_id VARCHAR, 
	shared_by_org_id VARCHAR, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_document_user_share UNIQUE (document_id, user_id), 
	FOREIGN KEY(document_id) REFERENCES docucr.documents (id) ON DELETE CASCADE, 
	FOREIGN KEY(user_id) REFERENCES docucr."user" (id) ON DELETE CASCADE, 
	FOREIGN KEY(shared_by_user_id) REFERENCES docucr."user" (id) ON DELETE SET NULL, 
	FOREIGN KEY(shared_by_org_id) REFERENCES docucr.organisation (id) ON DELETE SET NULL
);

CREATE TABLE docucr.external_shares (
	id UUID NOT NULL, 
	document_id INTEGER NOT NULL, 
	email VARCHAR NOT NULL, 
	password_hash VARCHAR NOT NULL, 
	token VARCHAR NOT NULL, 
	shared_by_user_id VARCHAR, 
	shared_by_org_id VARCHAR, 
	expires_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now(), 
	PRIMARY KEY (id), 
	FOREIGN KEY(document_id) REFERENCES docucr.documents (id), 
	FOREIGN KEY(shared_by_user_id) REFERENCES docucr."user" (id), 
	FOREIGN KEY(shared_by_org_id) REFERENCES docucr.organisation (id)
);

CREATE TABLE docucr.extracted_documents (
	id UUID NOT NULL, 
	document_id INTEGER NOT NULL, 
	document_type_id UUID NOT NULL, 
	template_id UUID, 
	page_range VARCHAR(50), 
	extracted_data JSON, 
	confidence FLOAT, 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	updated_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(document_id) REFERENCES docucr.documents (id), 
	FOREIGN KEY(document_type_id) REFERENCES docucr.document_types (id), 
	FOREIGN KEY(template_id) REFERENCES docucr.templates (id)
);

CREATE TABLE docucr.unverified_documents (
	id UUID NOT NULL, 
	document_id INTEGER NOT NULL, 
	suspected_type VARCHAR(100), 
	page_range VARCHAR(50), 
	extracted_data JSON, 
	status VARCHAR(20), 
	created_at TIMESTAMP WITHOUT TIME ZONE, 
	updated_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(document_id) REFERENCES docucr.documents (id)
);
CREATE TABLE docucr.client_location (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    client_id UUID NOT NULL,
    created_by VARCHAR,
    address_line_1 VARCHAR NOT NULL,
    address_line_2 VARCHAR,
    city VARCHAR NOT NULL,
    state_code VARCHAR NOT NULL,
    state_name VARCHAR,
    country VARCHAR DEFAULT 'United States',
    zip_code VARCHAR NOT NULL,
    is_primary BOOLEAN DEFAULT FALSE,

    -- Foreign Key Constraint
    CONSTRAINT fk_client
        FOREIGN KEY (client_id) REFERENCES docucr.client(id)
        ON DELETE CASCADE
);

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE docucr.provider_client_mapping (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    provider_id UUID NOT NULL,
    client_id UUID NOT NULL,
    location_id UUID,
    created_by VARCHAR,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    -- Foreign Key Constraints
    CONSTRAINT fk_provider 
        FOREIGN KEY (provider_id) REFERENCES docucr.provider(id),
    CONSTRAINT fk_client 
        FOREIGN KEY (client_id) REFERENCES docucr.client(id),
    CONSTRAINT fk_location 
        FOREIGN KEY (location_id) REFERENCES docucr.client_location(id)
);
-- Defer Circular Foreign Keys
ALTER TABLE docucr.client ADD CONSTRAINT fk_client_created_by FOREIGN KEY(created_by) REFERENCES docucr."user" (id);
ALTER TABLE docucr.client ADD CONSTRAINT fk_client_organisation_id FOREIGN KEY(organisation_id) REFERENCES docucr.organisation (id);
ALTER TABLE docucr.organisation ADD CONSTRAINT fk_organisation_client_id FOREIGN KEY(client_id) REFERENCES docucr.client (id);
ALTER TABLE docucr."user" ADD CONSTRAINT fk_user_client_id FOREIGN KEY(client_id) REFERENCES docucr.client (id);
ALTER TABLE docucr."user" ADD CONSTRAINT fk_user_created_by FOREIGN KEY(created_by) REFERENCES docucr."user" (id);
ALTER TABLE docucr."user" ADD CONSTRAINT fk_user_organisation_id FOREIGN KEY(organisation_id) REFERENCES docucr.organisation (id);

-- Alembic Versioning
CREATE TABLE docucr.alembic_version (
    version_num VARCHAR(32) NOT NULL, 
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);
INSERT INTO docucr.alembic_version (version_num) VALUES ('1b4d8bc8460e');


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

-- Reset Status Identity Sequence
SELECT setval('docucr.status_id_seq', (SELECT MAX(id) FROM docucr.status));

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
('52d854f8-09a4-49c6-817e-5e4e2783e06d', 'ORGANISATION_ROLE', 'Organisation level administrator', 1, TRUE, TRUE),
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
