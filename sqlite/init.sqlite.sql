INSERT INTO tenant (alias) VALUES ('wayfinder');
INSERT INTO company (tenant_id, alias) VALUES (1, 'fleetfoot');
INSERT INTO user (company_id, alias) VALUES (1, 'admin');
