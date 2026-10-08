-- Development RLS. Use dedicated migration/runtime roles in production.
ALTER TABLE projects ENABLE ROW LEVEL SECURITY;
ALTER TABLE projects FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS project_tenant_policy ON projects;
CREATE POLICY project_tenant_policy ON projects
USING (organization_id = NULLIF(current_setting('app.current_org_id', true), ''))
WITH CHECK (organization_id = NULLIF(current_setting('app.current_org_id', true), ''));
ALTER TABLE datasets ENABLE ROW LEVEL SECURITY;
ALTER TABLE datasets FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS dataset_tenant_policy ON datasets;
CREATE POLICY dataset_tenant_policy ON datasets
USING (organization_id = NULLIF(current_setting('app.current_org_id', true), ''))
WITH CHECK (organization_id = NULLIF(current_setting('app.current_org_id', true), ''));
