# API key migration checklist (RouteHub consumers)

Use this checklist when migrating `vepathos-api-doc` / `vepathos-router-client`
to the current RouteHub auth model.

## 1) Confirm DB has required schema/data

- `tenant`, `company`, and `api_key` tables must exist.
- Run:

```bash
docker exec routehub-db psql -U routehub_user -d routehub_db \
  -c "SELECT id, alias FROM tenant ORDER BY id;" \
  -c "SELECT id, tenant_id, alias FROM company ORDER BY id;" \
  -c "SELECT id, company_id, name, key_prefix, revoked_at FROM api_key ORDER BY id;"
```

## 2) Issue an API key for the target company

The raw key is shown once, then only its SHA-256 hash is stored.

```bash
RDBMS_URL=postgresql://routehub_user:routehub_pass@localhost:5433/routehub_db \
python scripts/issue_api_key.py issue --company-id <COMPANY_ID> --name "api-doc local dev"
```

Optional checks:

```bash
RDBMS_URL=postgresql://routehub_user:routehub_pass@localhost:5433/routehub_db \
python scripts/issue_api_key.py list --company-id <COMPANY_ID>
```

## 3) Configure consumers with the raw API key

- Set `ROUTEHUB_API_KEY=<raw key>` in each caller service.
- Send `Authorization: Bearer <raw key>` on every request.
- Do not use `X-RouteHub-Tenant-Id` (removed).
- Do not rely on the old shared `BEARER_TOKEN`.

## 4) Update HTTP client code in consumer apps

Minimal pattern:

```ts
const routeHubApiKey = process.env.ROUTEHUB_API_KEY;

if (!routeHubApiKey) {
  throw new Error("Missing ROUTEHUB_API_KEY");
}

const response = await fetch(`${routehubBaseUrl}/vehicles`, {
  method: "GET",
  headers: {
    Authorization: `Bearer ${routeHubApiKey}`,
    "Content-Type": "application/json",
    Accept: "application/json",
  },
});
```

## 5) Verify end-to-end behavior

- No header -> `401 Missing API key`
- Wrong/revoked key -> `401 Invalid API key`
- Valid key -> `200` and only rows for that `company_id`

Quick smoke test:

```bash
curl -i http://127.0.0.1:8001/vehicles
curl -i -H "Authorization: Bearer <RAW_KEY>" http://127.0.0.1:8001/vehicles
```

## 6) Rollback / rotation plan

- Create new key
- Deploy consumers with new key
- Revoke old key:

```bash
RDBMS_URL=postgresql://routehub_user:routehub_pass@localhost:5433/routehub_db \
python scripts/issue_api_key.py revoke --prefix <KEY_PREFIX>
```

## 7) Security hardening follow-up (Postgres RLS)

Apply schema migrations from `routehub-dbschem` (Atlas, includes RLS). The app
role must be `NOSUPERUSER NOBYPASSRLS` for RLS to enforce isolation in DB.
