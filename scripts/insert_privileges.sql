-- Insert master privileges
INSERT INTO docucr.privilege (id, name, description) VALUES
('priv_read', 'READ', 'Read access to resources'),
('priv_write', 'WRITE', 'Write/Create access to resources'),
('priv_delete', 'DELETE', 'Delete access to resources'),
('priv_admin', 'ADMIN', 'Full administrative access'),
('priv_none', 'NONE', 'No access to resources')
ON CONFLICT (name) DO NOTHING;
