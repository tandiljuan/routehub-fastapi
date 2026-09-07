-- ===========================================================================
-- smart_import_job — ownership record binding a Smart Import job to a workspace
--
-- Apply by hand on production (this deployment does not run Atlas):
--
--   psql "$RDBMS_URL" -f docs/smart-import-tenant.sql
--
-- Idempotent: safe to re-run. Verify at the bottom.
--
-- WHY THIS TABLE EXISTS
-- Smart Import keeps jobs in memory keyed by an opaque `imp_<hex>` id and is
-- workspace-blind: it will serve, download or re-geocode any id it is handed.
-- Without this row, any authenticated caller could read another workspace's
-- import — customer addresses and phone numbers — just by holding the id, which
-- travels in URLs, logs and support tickets. RouteHub is the only control.
--
-- The row is an authorization record, not a copy of the job: state, report and
-- files stay upstream. Rows are disposable — Smart Import purges the job itself
-- after SMART_IMPORT_JOB_TTL_HOURS, so a stale row just 404s upstream.
-- ===========================================================================

BEGIN;

CREATE TABLE IF NOT EXISTS "public"."smart_import_job" (
    -- Upstream id ("imp_" + 12 hex). Opaque here, never generated locally.
    "job_id"     VARCHAR(64)  NOT NULL,
    "company_id" INTEGER      NOT NULL,
    "filename"   VARCHAR(255) NULL,
    "created_at" TIMESTAMPTZ  NOT NULL DEFAULT now(),
    CONSTRAINT "smart_import_job_pkey" PRIMARY KEY ("job_id"),
    CONSTRAINT "smart_import_job_company_id_fkey"
        FOREIGN KEY ("company_id") REFERENCES "public"."company" ("id")
        ON UPDATE NO ACTION ON DELETE CASCADE
);

-- Every lookup is "this job, for this workspace".
CREATE INDEX IF NOT EXISTS "idx_smart_import_job_company"
    ON "public"."smart_import_job" ("company_id");

-- --------------------------------------------------------------------------
-- Row-level security, same shape as 20260702192100_row_level_security.sql.
-- FORCE applies the policy to the table owner too, so a query that forgets
-- `WHERE company_id = ?` still cannot cross workspaces. current_setting(...,
-- true) returns NULL when unset -> the policy excludes every row (fail closed).
-- --------------------------------------------------------------------------
ALTER TABLE "public"."smart_import_job" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "public"."smart_import_job" FORCE  ROW LEVEL SECURITY;

DROP POLICY IF EXISTS smart_import_job_tenant_isolation ON "public"."smart_import_job";
CREATE POLICY smart_import_job_tenant_isolation ON "public"."smart_import_job"
    USING      (company_id = current_setting('app.current_company', true)::int)
    WITH CHECK (company_id = current_setting('app.current_company', true)::int);

-- The app connects as a restricted role (see docs/security-tenancy.md). Grant
-- it the same rights it has on the other tenant tables.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'rh_app') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON "public"."smart_import_job" TO rh_app;
    END IF;
END $$;

COMMIT;

-- ===========================================================================
-- Verify
-- ===========================================================================
-- \d+ smart_import_job
--
-- Policy present and forced:
--   SELECT relname, relrowsecurity, relforcerowsecurity
--     FROM pg_class WHERE relname = 'smart_import_job';
--   -- expected: t | t
--
--   SELECT polname FROM pg_policy
--     WHERE polrelid = 'public.smart_import_job'::regclass;
--   -- expected: smart_import_job_tenant_isolation
--
-- Fail-closed check (run as rh_app, NOT as the owner/superuser — superusers and
-- BYPASSRLS roles ignore RLS entirely and this will look wrong):
--   RESET app.current_company;
--   SELECT count(*) FROM smart_import_job;   -- expected: 0
-- ===========================================================================
