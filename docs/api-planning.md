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
| Multiple instances of the same catalog vehicle with different limits | `POST /fleets` → repeat the same `id` with distinct `alias` per row | Each row becomes its own wire vehicle (see below) |
| Stops / km / priority per instance | `POST /fleets` → `vehicles[].route`, `behavior` | Stored as `run_profile` per link |
| Volume / weight on wire | `POST /vehicles` (catalog) | Unless overridden in lot `config.vehicles.*.capacity` |
| Rebalance flags & ratios (this lot) | `POST /lots` → `config.rebalance` | Per run |
| Start time & delivery windows (this lot) | `POST /lots` → `config.schedule` | Overlays server routing at plan time |
| Where the route ends, U-turns, one pass per city, ETA knobs | `POST /lots` → `config.routing` | See [Routing overlays](#routing-overlays) |
| U-turn rule for one vehicle type | `POST /vehicles` → `allow_uturns` | `null` inherits `config.routing.uturn_policy` |
| Zone label | `POST /lots` → `config.zone` | Default `MULTI` |
| Per-lot vehicle patches | `POST /lots` → `config.vehicles` | See hierarchy below |
| Engine tuning (2-opt, clustering sizes, parallelism) | **Not client-configurable** | Server defaults at `POST /plan` |
| Legacy global limits | `POST /lots` → `route_limits` | Deprecated; prefer fleet `run_profile`. Time bounds here still win over rebalance (see below) |

---

## `config.vehicles` hierarchy

`config.vehicles` is **optional**. When omitted, the plan uses only the fleet
`run_profile` and vehicle catalog.

```
config.vehicles
├── defaults          → same patch applied to every vehicle type in this lot
└── overrides[]       → patch targeting a fleet-vehicle instance (vehicle_id = alias/wire name)
                        or every instance of a catalog (vehicle_id = catalog id or catalog name);
                        alias matches beat catalog matches
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

**1. Fleet** with `route` and `behavior` per instance:

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

### Multiple instances of the same catalog vehicle

`alias` identifies a fleet-vehicle *instance* uniquely within a fleet. Repeat
the same catalog `id` with different aliases to give each instance its own
route/behavior limits — the optimizer treats them as separate wire vehicles.

```json
{
  "name": "mixed-vans",
  "vehicles": [
    { "id": "3", "qty": 1, "alias": "Van-A", "route": { "stops_max": 40 } },
    { "id": "3", "qty": 1, "alias": "Van-B", "route": { "stops_max": 80 } }
  ]
}
```

Legacy single-instance flotas (no `alias`) still work: the server defaults the
alias to the catalog vehicle name. `qty` remains meaningful — use it when
several units of the *same* alias share the same limits.

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

## Data model

What an integrator sends, and where it is stored. Ids in requests are strings;
the database keeps them as integers.

| Resource | Table | What you send | Where it lives |
|----------|--------|----------------|----------------|
| Vehicle type | `vehicle` | `POST /vehicles` | Columns. `allow_uturns` is its own boolean column (`null` = inherit the lot). `category_type: BICYCLE` is what makes the optimizer use the bike network. |
| Fleet | `fleet`, `fleet_vehicle` | `POST /fleets` | One row per instance (`alias` + `qty`). `route` and `behavior` are stored as JSON `run_profile`. |
| Stop | `delivery` | `POST /deliveries` or `/deliveries/bulk` | Columns for the stop itself. `extra` is JSON: the planner reads `lat`, `lng`, `zone`, and `packages`. |
| Lot | `delivery_lot` | `POST /lots` | `milestone_id`, `fleet_id`, state, and the legacy `route_*` columns (from `route_limits`). `config` is stored as JSON `config_data` (`LotConfig`). |
| Plan | `delivery_plan`, `delivery_path` | `POST /lots/{id}/plan` has no body | One plan row holds the optimizer session id and `totals_data` (JSON). Each route is a `delivery_path`; geometry and waypoints are JSON `route_data`. |

`config` does not get new columns when you add a routing knob. `route_end`,
`visit_zones_once`, `uturn_policy`, rebalance and schedule all sit inside
`config_data`. A plan the optimizer could not route stores `{code, message}`
in `totals_data` under `plan_error`; the API lifts that out as `error` and
does not mix it into `totals`.

`first_stop` is not stored. It is an instruction on `PATCH /lots/{id}/plan`
for that reoptimization only.

---

## Routing overlays

`config.routing` is optional. Unknown keys are dropped. Omitted fields are not
sent, and the optimizer keeps its own default.

```json
{
  "config": {
    "routing": {
      "service_time_min": 5,
      "avg_speed_kph": 25,
      "use_graph_travel_time": true,
      "uturn_policy": "no_uturn",
      "route_end": "point",
      "route_end_point": { "lat": 34.05, "lng": -118.24 },
      "visit_zones_once": true
    }
  }
}
```

| Field | Values | If omitted or invalid |
|-------|--------|------------------------|
| `uturn_policy` | `allow`, `no_uturn` | Optimizer default. A vehicle `allow_uturns` overrides this for that type. |
| `route_end` | `depot` (round trip), `last_stop` (open route), `point` | Round trip. Anything else is discarded. |
| `route_end_point` | `{lat, lng}` inside the world | Required when `route_end` is `point`. A broken point is discarded and the route returns to the depot. |
| `visit_zones_once` | boolean | Each city's stops in one pass. The optimizer only applies it on country routes, and only if its switch is on. |
| `use_graph_travel_time` | boolean | `false` is a real value and is sent. |
| `service_time_min`, `avg_speed_kph` | number | Minutes at each stop, and average speed in km/h. |

The same fields are sent again when the lot is reoptimized.

---

## Route duration the optimizer receives

The optimizer takes **one** time window for every route. The API fills it from
the first source that has a value (`0` counts; only a missing value is skipped):

```
lot route_limits.time_*     (Duration card)
  > config.rebalance.rebalance_by_time.min/max_time_minutes_per_route
  > strictest per-vehicle route.time_*   (lowest min, lowest max)
  > config.vehicles.defaults.route.time_*
```

Per-vehicle limits come from `config.vehicles.overrides` or, if that type has
no override, from the fleet `run_profile`. A bike capped at 300 minutes and a
van at 360, with no Duration card and no time branch, sends **300** for the
whole fleet. A lot with no per-vehicle time limits is unchanged.

---

## Package volume

The optimizer computes volume only from `dimensions` (length, width, height).
`PlanPackage` has no volume field.

Put packages on the stop, in `extra`:

```json
{
  "extra": {
    "lat": 40.71,
    "lng": -74.0,
    "packages": [
      { "package_id": "P-1", "weight_kg": 20.8, "volume_cm3": 174787 }
    ]
  }
}
```

If `volume_cm3` is set and length, width and height are not all present and
positive, the API sends the equivalent cube (side = cube root, two decimals).
Complete dimensions win over `volume_cm3`. Zero, negative or non-numeric
volume is ignored, and the package goes out with no dimensions.

---

## Reoptimize with a fixed first stop

`PATCH /lots/{id}/plan` accepts an optional `first_stop` on each route: the id
of one delivery in that route's `deliveries`. The route leaves the depot
toward that stop and the optimizer orders the rest.

```json
[
  { "id": "15", "deliveries": ["101", "102", "103"], "first_stop": "102" }
]
```

`422` if `first_stop` is not one of that route's deliveries. Omit the field
and the optimizer chooses the whole order. The optimizer ignores it while
`ROUTE_FIXED_FIRST_STOP` is off.

---

## When the optimizer cannot route

A session the optimizer reports as `failed` (HTTP 200 with `status=failed`)
is not an empty success.

| Situation | Lot state | What you get |
|-----------|-----------|----------------|
| First plan cannot be routed | `CANCELED` | `GET /lots/{id}/plan` returns the plan with `routes: null` and `error: { "code", "message" }`. Later reads return the same `error`. |
| Progress poll after that | `CANCELED` with a stored error | `GET /lots/{id}/plan/status` returns **410** with `detail` (the message) and `error_code`. |
| Lot canceled without a stored error | `CANCELED` | `/plan/status` stays **409**. |
| Reoptimize failed | back to `PROCESSED` | That `GET /plan` returns the previous routes plus `error`. The error is not stored. |
| Optimizer unreachable | unchanged | **502**. |

Successful plans do not include `error`.

Waypoints in `delivery_paths[].optimized_waypoints` may include `access_point`
(`[lat, lng]` of the nearest drivable point) and `walk_m` (meters on foot from
there to the stop). They are present only when the optimizer computed them.

---

## Swagger / OpenAPI

The file to give an integrator is `vepathos-api-doc/openapi.json` (OpenAPI 3.1,
version **0.27.0**). It is the contract the docs site renders. Do not hand
over `routehub-openapi` (`rhbundle.yaml` is still 0.20.0) or the local
`openapi_bc.json` snapshot.

With the API running locally (`ENVIRONMENT=LCL`), the same schema is at
`/openapi.json`.

In `/docs`, use the **Examples** dropdown on:

- `POST /fleets` — composition-only vs full `run_profile`
- `POST /lots` — required-only vs config overrides vs rebalance
- `PATCH /lots` — partial config merge

The schema tree still lists optional nested fields; examples show what to send in
practice.
