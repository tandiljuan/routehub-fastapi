INSERT INTO tenant (alias) VALUES ('wayfinder');
INSERT INTO tenant_user (tenant_id, alias) VALUES (1, 'admin');
INSERT INTO company (tenant_id, alias) VALUES (1, 'fleetfoot');
INSERT INTO company_user (company_id, alias) VALUES (1, 'admin');
