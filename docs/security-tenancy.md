# Security & multi-tenancy

How RouteHub authenticates callers and isolates workspaces.

## Current model — per-app API keys (Option A)

RouteHub uses **one credential** that does authentication *and* workspace scoping
in a single step:

- The caller sends an **API key** as `Authorization: Bearer rh_live_<random>`.
- `libs/authorization/authorization.py` hashes it (`sha256`) and looks it up in
  the `api_key` table (`models/api_key.py`). The matching row's `company_id` is
  the request's workspace. No match / revoked / missing → `401` (fail closed).
- The key is bound to exactly one company, so the workspace is **derived from a
  verified credential**, never from a client-supplied value. This satisfies the
  multi-tenancy standard (OWASP: "don't trust a client-supplied tenant id").
- Every route still asserts/filters by that `company_id`; cross-workspace access
  returns `404` (a foreign id is indistinguishable from a missing one).

The same dependency (`authorization`) is the app-wide guard **and** `CompanyDep`;
FastAPI caches it per request, so the DB lookup runs once.

### Why this design

| Property | How |
|---|---|
| Key never stored | Only `sha256(key)` + a short `key_prefix` for display/logs |
| Identifiable / scannable | `rh_live_` prefix (env-tagged, secret-scanner friendly) |
| Revocable | `revoked_at` column; revoked keys fail instantly |
| Rotatable | issue new + revoke old |
| Auditable | `key_prefix`, `created_at`, `last_used_at`, `name` |
| One secret | the key authenticates AND scopes — no separate shared token |

### Issuing / revoking keys

Keys are managed with the CLI (no admin HTTP surface):

```bash
RDBMS_URL=... python scripts/issue_api_key.py issue --company-id 1 --name "router-client prod"
RDBMS_URL=... python scripts/issue_api_key.py list --company-id 1
RDBMS_URL=... python scripts/issue_api_key.py revoke --prefix rh_live_AbCd
```

The full key is printed **once** at creation and never again.

### Schema

Table `api_key(id, company_id, name, key_prefix, key_hash UNIQUE, created_at,
last_used_at, revoked_at)` — defined in `routehub-dbschem/schema.dbml`, applied
via Atlas (`20260702192000_lot_config_plan_metrics_api_key.sql`). RLS:
`20260702192100_row_level_security.sql` in the same repo.

Table `smart_import_job(job_id PK, company_id, filename, created_at)` binds a
Smart Import job to the workspace that created it. Smart Import itself is
workspace-blind — it serves any `imp_<hex>` id it is handed — so this row is the
only control between one workspace and another's customer addresses. Applied by
hand in production: `psql "$RDBMS_URL" -f docs/smart-import-tenant.sql`
(that file creates the table and enrolls it in RLS).

## Migration note (hard cut)

The previous `X-RouteHub-Tenant-Id` header and the single shared `BEARER_TOKEN`
were **removed**. Every caller must now present its own API key. There is no
header fallback — clients that have not migrated will get `401`.

## Roadmap

| Phase | What | Binds company to credential? | Status |
|---|---|---|---|
| 1 | Perimeter + mandatory header + hardened token (bridge) | gateway-delegated | superseded |
| 1.5 / 2a | **API keys hashed in DB** | yes (DB lookup) | ✅ done |
| 3 | **Postgres Row-Level Security (RLS)** | defense-in-depth | ✅ done |
| 2b | JWT with `company_id` claim, signed by gateway/IdP | yes (signature) | future |

## Defense-in-depth — Postgres RLS (implemented)

Every tenant table is enrolled in row-level security scoped to the GUC
`app.current_company`, which the app sets per request from the API key's company
(`libs/rls.py`; Atlas migration `20260702192100_row_level_security.sql` in
`routehub-dbschem`). A query that forgets
`WHERE company_id = ?` then returns only the current company's rows — or none if
the GUC is unset (fail closed). `FORCE` makes the policy apply to the table owner
too. Verified against Postgres: cross-company reads return 0 rows and inserts for
another company fail the `WITH CHECK`.

Enrolled: `vehicle, fleet, driver, milestone, delivery, delivery_lot,
smart_import_job` (direct `company_id`) and `delivery_plan, delivery_path` (via
subquery on their lot).
Not enrolled: `api_key` (read before the company is known; gated by the secret
key_hash), `company`/`tenant` (deployment catalog), and pure link tables (reached
only via their RLS-protected parents — can be enrolled later if desired).

### ⚠️ Operational requirement: the app must NOT connect as a superuser

Postgres **superusers and roles with `BYPASSRLS` ignore RLS entirely** (even with
`FORCE`). The default `routehub_user` from the postgres image is a superuser, so
**RLS is inert until the app connects as a dedicated, restricted role**:

```sql
CREATE ROLE rh_app LOGIN PASSWORD '<secret>' NOSUPERUSER NOBYPASSRLS;
GRANT USAGE ON SCHEMA public TO rh_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO rh_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO rh_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO rh_app;
```

Then point the app's `RDBMS_URL` at `rh_app`. Keep migrations/admin scripts on the
owner/superuser role. (Caveat: with pgbouncer in *transaction* pooling, the
transaction-local `set_config(..., true)` we use is the correct choice — a
session-level GUC would not be safe there.)

### Tests

`tests/test_rls_postgres.py` validates enforcement against a real Postgres
(fail-closed, cross-company reads = 0, `WITH CHECK` blocks foreign writes,
superuser bypass, and the full API-key → GUC request path). It is **skipped**
unless a superuser URL is provided; it provisions and drops its own throwaway db
and restricted role:

```bash
RLS_TEST_DATABASE_URL="postgresql://routehub_user:routehub_pass@localhost:5433/postgres" \
    python -m pytest tests/test_rls_postgres.py -v
```

The SQLite suite (`python -m pytest tests/`) skips these 10 tests automatically.

## Rate limiting (domain 5)

Per-tenant rate limiting / quotas are handled at the **gateway** (vepathos-api-doc
/ reverse proxy), not in RouteHub, to keep the API stateless and Redis-free. This
is a deliberate placement of the OWASP "noisy neighbor" control, not a gap.

### Phase 2b — JWT (optional evolution)

When the gateway/IdP issues real JWTs, swap the DB lookup for signature
verification (RS256) and read `company_id` from the claim — stateless, no
per-request DB hit, multi-user/role-ready. The `bearerAuth` scheme in the
OpenAPI already fits.

### Phase 3 — RLS (defense-in-depth)

`SET app.current_company = :id` per transaction + Postgres RLS policies
(`company_id = current_setting('app.current_company')::int`) on tenant tables, so
a missing `WHERE company_id = ?` in code can't leak across tenants.
