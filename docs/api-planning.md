# Planning API — quick guide

How to call the API to create a lot and run the optimizer. For exhaustive
scenario coverage see `lot_config_scenarios.md` (internal QA).

## Call sequence

```
POST /vehicles          (catalog: volume, weight, consumption)
POST /fleets            (composition + optional route/behavior per type)
POST /milestones        (depot / origin)
POST /deliveries/bulk   (stops)
POST /lots              (link milestone + fleet + deliveries + optional config)
POST /lots/{id}/plan    (no body — builds wire, queues optimizer)
GET  /lots/{id}/plan    (poll until routes are ready)
```

Optional later: `PATCH /fleets/{id}`, `PATCH /lots/{id}`, then `POST /plan` again.

---

## What you can configure (and where)

| Concern | Configure on | Notes |
|---------|--------------|-------|
| Vehicle types & quantities | `POST /fleets` → `vehicles[].id`, `qty` | **Required** for every plan |
| Stops / km / priority per type (default for all lots) | `POST /fleets` → `vehicles[].route`, `behavior` | Stored as `run_profile` |
| Volume / weight on wire | `POST /vehicles` (catalog) | Unless overridden in lot `config.vehicles.*.capacity` |
| Rebalance flags & ratios (this lot) | `POST /lots` → `config.rebalance` | Per run |
| Start time & delivery windows (this lot) | `POST /lots` → `config.schedule` | Overlays server routing at plan time |
| Zone label | `POST /lots` → `config.zone` | Default `MULTI` |
| Per-lot vehicle patches | `POST /lots` → `config.vehicles` | See hierarchy below |
| Clustering / routing / settings (engine) | **Not client-configurable** | Server env / defaults at `POST /plan` |
| Legacy global limits | `POST /lots` → `route_limits` | Deprecated; prefer fleet `run_profile` |

---

## `config.vehicles` hierarchy

`config.vehicles` is **optional**. When omitted, the plan uses only the fleet
`run_profile` and vehicle catalog.

```
config.vehicles
├── defaults          → same patch applied to every vehicle type in this lot
└── overrides[]       → patch for one type (vehicle_id = catalog id or wire name)
    └── vehicle_id
        capacity      → volume_max, weight_max (optional)
        route         → stops, distance, time (optional)
        behavior      → priority, overflow_vehicle (optional)
```

**Merge order** (highest wins per field):

```
overrides[vehicle_id]  >  defaults  >  fleet.run_profile  >  route_limits  >  plan fallback
```

`config.vehicles` does **not** add or remove fleet members — it only overrides
limits/behavior for types already in `fleet_id`.

---

## Recipe A — Fleet carries everything (recommended)

**1. Fleet** with `route` and `behavior` per type:

```json
{
  "name": "DBO1",
  "vehicles": [
    {
      "id": "3",
      "qty": 2,
      "route": { "stops_min": 60, "stops_max": 80 },
      "behavior": { "priority": 1, "overflow_vehicle": true }
    }
  ]
}
```

**2. Lot** — required fields only:

```json
{
  "milestone_id": "1",
  "fleet_id": "1",
  "deliveries": ["101", "102", "103"]
}
```

**3. Plan** — `POST /lots/1/plan` (empty body).

---

## Recipe B — Fleet is composition; limits per lot

Fleet with only `id` + `qty`. Lot carries overrides:

```json
{
  "milestone_id": "1",
  "fleet_id": "1",
  "deliveries": ["101", "102"],
  "config": {
    "vehicles": {
      "defaults": {
        "route": { "stops_max": 90 }
      },
      "overrides": [
        {
          "vehicle_id": "7",
          "route": { "stops_min": 35 },
          "behavior": { "overflow_vehicle": true }
        }
      ]
    }
  }
}
```

Type `3` gets `stops_max: 90` from defaults; type `7` also gets `stops_min: 35`
and `overflow_vehicle: true` from its override.

---

## Recipe C — Rebalance & schedule (this lot only)

```json
{
  "milestone_id": "1",
  "fleet_id": "1",
  "deliveries": ["101", "102"],
  "config": {
    "rebalance": {
      "rebalance_by_size": { "enabled": true },
      "rebalance_by_volume": {
        "enabled": true,
        "min_volume_capacity_ratio_vehicle": 0.1,
        "max_volume_capacity_ratio_vehicle": 0.925
      }
    },
    "schedule": {
      "start_at": "2026-06-09T12:00:00Z",
      "respect_delivery_windows": true
    },
    "zone": "MULTI"
  }
}
```

---

## PATCH semantics

`PATCH /lots/{id}` **deep-merges** `config` into stored `config_data`. Send only
the branches you want to change:

```json
{
  "config": {
    "vehicles": {
      "overrides": [
        { "vehicle_id": "3", "route": { "stops_min": 55 } }
      ]
    }
  }
}
```

`PATCH /fleets/{id}` replaces fleet vehicle links; the **next** `POST /plan` reads
the updated `run_profile`.

---

## Swagger / OpenAPI

In `/docs`, use the **Examples** dropdown on:

- `POST /fleets` — composition-only vs full `run_profile`
- `POST /lots` — required-only vs config overrides vs rebalance
- `PATCH /lots` — partial config merge

The schema tree still lists optional nested fields; examples show what to send in
practice.
