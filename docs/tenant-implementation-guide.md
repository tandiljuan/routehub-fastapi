# Tenant implementation guide (RouteHub)

This document explains the multi-tenant model implemented in `routehub-fastapi`,
how API keys are issued/validated, how tenant/company data is stored, how clients
must be configured, and how to inspect/reset the database.

---

## 1) What changed

Previous model (deprecated):

- Shared `BEARER_TOKEN`
- Client-provided tenant header (`X-RouteHub-Tenant-Id`)

Current model (implemented):

- Per-application API keys
- Keys are sent as `Authorization: Bearer <raw_key>`
- API hashes the raw key with SHA-256 and validates against table `api_key`
- The request workspace is derived from the validated key's `company_id`
- No tenant/workspace header is trusted from clients

Important: JWT signed claims (`company_id` in JWT) are not yet implemented in this
repository. Current production path is DB-backed API key lookup.

---

## 2) Core architecture

### 2.1 Authentication + workspace resolution

Entry point: `libs/authorization/authorization.py`

- Reads bearer token from `Authorization` header
- Computes `sha256(raw_key)`
- Queries `api_key` with:
  - matching `key_hash`
  - `revoked_at IS NULL`
- On success:
  - returns `company_id`
  - sets request-scoped company context (`set_current_company`)
  - applies company to DB session for RLS (`apply_company_to_session`)
- On failure:
  - `401 Missing API key` if absent
  - `401 Invalid API key` if not found/revoked

### 2.2 Route protection

Entry point: `main.py`

- Global dependency: `dependencies=[Depends(auth)]`
- Every route requires valid bearer credentials

### 2.3 Company scoping in routes

Entry point: `libs/tenant/context.py`

- `CompanyDep = Depends(authorization)`
- Routes use `company_id` from dependency, not from client input
- Helper checks return `404` on cross-tenant access (fail closed / no info leak)

### 2.4 DB defense-in-depth (RLS)

Entry point: `libs/rls.py` — policies applied via `routehub-dbschem` migration
`20260702192100_row_level_security.sql`

- Sets transaction-local GUC: `app.current_company`
- RLS policies can enforce `company_id` scope in Postgres
- Critical caveat: RLS is bypassed by superusers/BYPASSRLS roles
- App role should be `NOSUPERUSER NOBYPASSRLS` for true enforcement

---

## 3) Data model (tenant/auth related)

### 3.1 `tenant`

- `id` (PK)
- `alias` (unique)

Migration: `routehub-dbschem` — `20260123211746_initial_migration.sql`

### 3.2 `company`

- `id` (PK)
- `tenant_id` (FK -> `tenant.id`)
- `alias`

Migration: `routehub-dbschem` — `20260123211746_initial_migration.sql`

### 3.3 `api_key`

- `id` (PK)
- `company_id` (FK -> `company.id`)
- `name` (human label)
- `key_prefix` (display/log identifier)
- `key_hash` (SHA-256 of full raw key, unique)
- `created_at`
- `last_used_at` (optional)
- `revoked_at` (optional)

Migration: `routehub-dbschem` — `20260702192000_lot_config_plan_metrics_api_key.sql`

Security note:

- Raw key is never stored in DB
- Raw key is shown once at creation

---

## 4) End-to-end request flow

1. Client sends `Authorization: Bearer rh_live_...`
2. API validates key in `api_key`
3. API resolves `company_id` from validated key
4. Routes query only tenant-owned records
5. Optional Postgres RLS blocks cross-company rows at DB layer

Result: tenant isolation is credential-bound, not header-bound.

---

## 5) Step-by-step: setup from zero

## 5.1 Start containers

```bash
docker compose up -d
```

DB container in local override is typically exposed at `localhost:5433`.

## 5.2 Ensure schema exists

Schema is owned by **routehub-dbschem**. See `docs/DEPLOYMENT.md` in that repo.

Quick local Postgres path:

```bash
cd ../routehub-dbschem
export DATABASE_URL="postgresql://routehub_user:routehub_pass@localhost:5433/routehub_db"
atlas migrate apply --url "$DATABASE_URL"
psql "$DATABASE_URL" -f seeds/dev_seed.sql
```

---

## 6) API key lifecycle

All key operations are done with:

- `scripts/issue_api_key.py`

It requires:

- `RDBMS_URL=...`
- `--company-id` as integer (not alias string)

### 6.1 Issue key

```bash
RDBMS_URL=postgresql://routehub_user:routehub_pass@localhost:5433/routehub_db \
python scripts/issue_api_key.py issue --company-id 1 --name "vepathos api-doc tenant"
```

The command prints the raw key once. Save it in secrets/env immediately.

### 6.2 List keys

```bash
RDBMS_URL=postgresql://routehub_user:routehub_pass@localhost:5433/routehub_db \
python scripts/issue_api_key.py list --company-id 1
```

### 6.3 Revoke key

```bash
RDBMS_URL=postgresql://routehub_user:routehub_pass@localhost:5433/routehub_db \
python scripts/issue_api_key.py revoke --prefix rh_live_AbCd
```

---

## 7) Where to configure `ROUTEHUB_API_KEY`

Server (`routehub-fastapi`) validates incoming keys. It does not need a static
local API key to authenticate itself.

Set `ROUTEHUB_API_KEY` in callers (consumers):

- `vepathos-api-doc`
- `vepathos-router-client`
- local scripts that call RouteHub (`scripts/test_plan_flow.py`)

### 7.1 Local script usage

```bash
export ROUTEHUB_API_KEY="rh_live_..."
python scripts/test_plan_flow.py --scenario 05 --wire-only
```

### 7.2 Consumer env example

```env
ROUTEHUB_BASE_URL=http://127.0.0.1:8001
ROUTEHUB_API_KEY=rh_live_...
```

### 7.3 HTTP client example

```ts
const apiKey = process.env.ROUTEHUB_API_KEY;
if (!apiKey) throw new Error("Missing ROUTEHUB_API_KEY");

const response = await fetch(`${baseUrl}/vehicles`, {
  headers: {
    Authorization: `Bearer ${apiKey}`,
    Accept: "application/json",
    "Content-Type": "application/json",
  },
});
```

---

## 8) Database inspection

## 8.1 Connect with psql

```bash
docker exec -it routehub-db psql -U routehub_user -d routehub_db
```

## 8.2 Useful queries

```sql
SELECT id, alias FROM tenant ORDER BY id;
SELECT id, tenant_id, alias FROM company ORDER BY id;
SELECT id, company_id, name, key_prefix, key_hash, revoked_at, created_at
FROM api_key
ORDER BY id;
```

Key point:

- Hash is stored in `api_key.key_hash`
- Raw key is never persisted

## 8.3 GUI connection (DBeaver/TablePlus/pgAdmin)

- Host: `localhost`
- Port: `5433`
- Database: `routehub_db`
- User: `routehub_user`
- Password: `routehub_pass`

Note: this repo does not use Prisma (`schema.prisma` is absent), so Prisma Studio
is not available directly here.

---

## 9) Reset procedures

### 9.1 Soft reset (only keys)

```bash
docker exec routehub-db psql -U routehub_user -d routehub_db \
  -c "TRUNCATE TABLE api_key RESTART IDENTITY;"
```

### 9.2 Full reset (wipe all DB data)

```bash
docker compose down -v
docker compose up -d db api
```

Then run section 5 again to reinitialize schema and migrations.

---

## 10) Validation checklist

- `GET /vehicles` without header -> `401 Missing API key`
- `GET /vehicles` with invalid key -> `401 Invalid API key`
- `GET /vehicles` with valid key -> `200` and company-scoped data
- Cross-company direct ID access returns `404`
- Key revocation causes immediate `401` for that key

Quick smoke:

```bash
curl -i http://127.0.0.1:8001/vehicles
curl -i -H "Authorization: Bearer <RAW_KEY>" http://127.0.0.1:8001/vehicles
```

---

## 11) Common errors and fixes

`error: argument --company-id: invalid int value`

- Cause: passed alias string instead of numeric id
- Fix: use integer company id from `company` table

`401 Missing API key`

- Cause: request sent without `Authorization`
- Fix: send `Authorization: Bearer <raw_key>`

`401 Invalid API key`

- Cause: wrong key, revoked key, or key not present in `api_key`
- Fix: issue new key and update consumer env

RLS appears inactive

- Cause: Atlas migration `20260702192100_row_level_security.sql` not applied and/or app connects as superuser
- Fix: `atlas migrate apply` from routehub-dbschem and use restricted role (`NOSUPERUSER NOBYPASSRLS`)

---

## 12) Related documentation

- `docs/security-tenancy.md` (security rationale, OWASP mapping, roadmap)
- `docs/api-key-migration-checklist.md` (quick migration steps)
