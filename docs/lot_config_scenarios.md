# Fleet, lot config, and optimizer wire — public API guide

How to combine the current endpoints to build the outbound optimizer request
(`POST /lots/{id}/plan` → wire). Each catalog row maps to a scenario in
`scripts/explore_wire_request_matrix.py` and, when applicable, to
`scripts/test_plan_flow.py --scenario …`.

---

## Do we cover all public API variants?

**Yes — the scenario matrix covers the relevant public API surface** (patterns A–J,
legacy columns, units, errors, PATCH flows). Summary:

| Area | Covered? | Scenarios | Notes |
|------|----------|-----------|-------|
| Catalog before fleet | Yes (local) | `00` | `POST /vehicles` only; no wire |
| Fleet without lot | Partial | `00b` | Local vehicle preview; real API needs lot + deliveries |
| Fleet `run_profile` (prod) | Yes | `01`, `07`, `10` | Pattern A (recommended) |
| Fleet catalog + qty only | Yes | `02`, `03`, `05` | Fallback or `route_limits` / overrides |
| `config.vehicles.overrides` | Yes | `04`, `05`, `08`, `09`, `18` | Includes override via `PATCH /lots` |
| `config.vehicles.defaults` | Yes | `06`, `14`, `15` | Global lot-level patch |
| Precedence override > fleet > legacy | Yes | `09` | Pattern G |
| Legacy `route_limits` (global) | Yes | `03`, `09`, `14` | Stops/km/time on the lot |
| `config.rebalance` + `schedule` + `zone` | Yes | `01`, `10`, `15`, `18`, **`20`**, **`21`** | Includes merge via `PATCH /lots` |
| Units (`METER`, `HOUR`) | Yes | `14` | Converted to km / minutes in wire |
| Rebalance time vs route time | Yes | `15` | `rebalance_by_time` branch wins |
| Rebalance by distance (flag) | Yes | **`20`** | Flag on wire; km limits from fleet |
| Rebalance by weight (ratios) | Yes | **`21`** | Flag + min/max weight ratios in wire |
| Rebalance volume **explicit off** | Yes | **`24`** | `{ enabled: false }` while weight on |
| Rebalance size **explicit off** | Yes | **`25`** | `{ enabled: false }` while volume on |
| Rebalance **all flags off** | Yes | **`26`** | Five branches `{ enabled: false }` |
| qty = 0 in fleet | Yes | `07` | Type in wire with `quantity: 0` |
| Anti-pattern: override without fleet link | Yes | `08` | Wire yes; route persistence fragile |
| Clustering / routing / settings passthrough | Yes | `11` | Required today for `POST /plan` |
| Clustering auto (legacy formula) | Yes | **`22`** | When `min/max` or whole `clustering` omitted |
| Preprocessing batch auto (legacy) | Yes | **`12`**, **`22`**, **`23`** | `max_size_cluster × 3` when batch omitted |
| Legacy clustering → error | Yes | `12` | `POST /plan` → **422** |
| **`PATCH /fleets/{id}`** after lot exists | Yes | **`17`** | Next plan reads updated fleet |
| **`PATCH /lots/{id}`** before plan | Yes | **`18`** | Deep merge into `config_data` |
| **`vehicle_limits` legacy** | Yes | **`19`** | Stored on lot; **does not** affect wire |
| **Catalog `weight`/`volume` → wire caps** | Yes | **`27`** | No `capacity` override; asserts `max_weight`/`max_volume` |
| **`config.vehicles.*.capacity` override** | Yes | **`28`** | Override beats catalog for one type |
| **Catalog without volume/weight** | Yes | **`29`** | Wire omits `max_volume`/`max_weight` |
| **`config.rebalance` omitted** | Yes | **`30`** | Adapter default: size=true, rest false |
| **Override by wire_type name (`v3`)** | Yes | **`31`** | Same as catalog id `67` (scenario 04) |
| **Weight rebalance `{enabled:true}` only** | Yes | **`32`** | Wire ratios 0.01 / 0.95 (defaults) |
| **Alternate fleet totals (50 / 70)** | Yes | **`33`**, **`34`** | Same run_profile; qty differs from DBO1 (60) |
| **Time rebalance `{enabled:true}` only** | Yes | **`35`** | Wire min/max **60 / 420** min (defaults) |
| **Volume rebalance `{enabled:true}` only** | Yes | **`36`** | Wire ratios **0.1 / 0.925** (defaults) |
| **Remaining gaps** | | | |
| `PATCH /vehicles/{id}` (catalog) | No | — | Changes volume/weight in wire; no scenario |
| `config.vehicles.defaults.behavior` only | Partial | — | Same mechanism as `06`; no dedicated scenario |

**Getting started:** use `01` + `11` (clustering/routing/settings) + `12` (validation).
Use `17`–`19` when mutating fleet/lot after create or when clients still send
`vehicle_limits`.

---

## End-to-end public API flow (greenfield)

Minimum sequence until routes are returned:

```
1. POST /vehicles (×N)     → catalog (volume, weight, consumption)
2. POST /fleets            → composition (qty) + optional run_profile (route, behavior)
3. POST /milestones        → depot / origin
4. POST /deliveries/bulk   → stops (chunk if needed)
5. POST /lots              → milestone_id + fleet_id + deliveries[] + config (+ optional legacy)
6. POST /lots/{id}/plan    → no body; builds wire and queues optimizer
7. GET  /lots/{id}/plan    → poll state / routes
```

Optional mutations: `PATCH /fleets/{id}`, `PATCH /lots/{id}`, `PATCH /lots/{id}/plan`
(manual routes).

**Golden rule:** vehicle types and quantities always come from `fleet_id`.
`config.vehicles` does not add or remove fleet members — it only patches limits/behavior
for that run.

---

## Choosing your API flow (what to send where)

Use this to pick endpoints and bodies without reading the full scenario catalog.

### Step 1 — Always create catalog + fleet + lot skeleton

```
POST /vehicles (×N)     → volume, weight, consumption (wire caps for volume/weight)
POST /fleets            → vehicles[].id, qty  (+ route/behavior = run_profile)
POST /milestones
POST /deliveries/bulk
POST /lots              → milestone_id, fleet_id, deliveries[]
```

### Step 2 — Where do vehicle **stops / km / priority** come from?

| Your need | Send on | Example scenario |
|-----------|---------|------------------|
| Same limits every run for this fleet | **`POST /fleets`** → `vehicles[].route`, `behavior` | **01** (pattern A) |
| Fleet is only composition; limits per lot | **`POST /lots`** → `config.vehicles.overrides` | **05** |
| Tweak one type for one lot | **`POST /lots`** → `overrides[{ vehicle_id, route }]` | **04** |
| Same patch for all types in one lot | **`POST /lots`** → `config.vehicles.defaults.route` | **06** |
| Legacy global caps (all vehicles equal) | **`POST /lots`** → `route_limits` | **03** |
| Override beats fleet beats legacy | All three layers | **09** (pattern G) |
| Change fleet after lot exists | **`PATCH /fleets/{id}`** then plan again | **17** |
| Change lot config after create | **`PATCH /lots/{id}`** (deep merge) | **18** |
| No route anywhere → plan computes fallback stops | Fleet id+qty only, empty vehicles config | **02** |
| Volume/weight on wire from catalog only | Fleet + lot **without** `config.vehicles.capacity` | **27** |
| Override catalog caps for one type | **`config.vehicles.overrides[].capacity`** | **28** |
| Vehicle catalog without volume/weight | `POST /vehicles` omits volume/weight | **29** |

**Precedence (one field, one winner):**

```
override[vehicle_id]  >  defaults  >  fleet.run_profile  >  route_limits  >  plan fallback
```

### Step 3 — Rebalance / schedule (this lot only)

| Your need | Send on | Example |
|-----------|---------|---------|
| Prod-like: size on, rest off (implicit) | `config.rebalance.rebalance_by_size: { enabled: true }` | **01** |
| Volume ratios | `rebalance_by_volume` + numeric ratios | **10**, **18** |
| Turn on weight / distance / time | matching branch `{ enabled: true }` (+ params) | **21**, **20**, **15** |
| **Explicitly disable** a dimension | `{ enabled: false }` on that branch | **24**, **25**, **26** |
| Schedule / time slot | `config.schedule` (`start_at`, `time_windows`) | **10** |

See [Rebalance dimensions](#rebalance-dimensions-configrebalance) below for the full flag matrix.

### Step 4 — Optimizer engine tuning (server-controlled)

| Blob | Public API? | Behavior |
|------|-------------|----------|
| `config.clustering` | **No** | **Ignored** if sent; resolved at plan time from `PLAN_CLUSTERING_JSON` env or server defaults. `min`/`max` auto from deliveries ÷ fleet qty when omitted (**22**) |
| `config.routing` | **No** | **Ignored** if sent; server defaults + `config.schedule` overlay |
| `config.settings` | **No** | **Ignored** if sent; server defaults; `preprocessing_batch_size` auto from cluster max |

Public clients send only `rebalance`, `schedule`, `zone`, and fleet `run_profile`.
Matrix scenario **11** tests engine overlays via `internal_config` (deploy/env), not `POST /lots`.

### Step 5 — Plan

```
POST /lots/{id}/plan    → no body
GET  /lots/{id}/plan    → poll
```

**Mutations:** `PATCH /fleets` updates what the **next** plan reads for qty/route.
`PATCH /lots` deep-merges `config` — use for mid-flight overrides (**18**).

---

## Where each setting lives

| Concept | API location | Purpose |
|---------|--------------|---------|
| **Fleet composition** | `POST /fleets` → `vehicles[].id`, `vehicles[].qty` | Which types and how many |
| **Operational defaults** | `POST /fleets` → `vehicles[].route`, `vehicles[].behavior` | Per-type route limits and planner behavior (`run_profile`) |
| **Run knobs** | `POST /lots` → `config.rebalance`, `config.schedule`, `config.zone` | This run only |
| **Per-lot vehicle patches** | `POST /lots` → `config.vehicles` | Sparse overrides when the same fleet must behave differently in one lot |
| **Legacy (deprecated)** | `POST /lots` → `route_limits`, `vehicle_limits` | Old global columns; accepted, hidden from Swagger |
| **Optimizer tuning (internal)** | `POST /lots` → `config.clustering`, `config.routing`, `config.settings` | Optional overrides when sent; hidden from public OpenAPI |

---

## Precedence (per vehicle field)

Highest priority wins:

```
config.vehicles.overrides[vehicle_id]   →  wins over everything else (per type)
config.vehicles.defaults                →  patch all fleet types in this lot
fleet.run_profile (route / behavior)    →  fleet operational defaults
lot.route_limits (legacy columns)       →  same limit for every vehicle
POST /plan fallback                     →  stops when no route in any layer
catalog                                 →  volume, weight, consumption (not stops)
```

**Volume / weight on the wire** (separate chain — fleet `run_profile` does not set these):

```
config.vehicles.overrides[].capacity    →  weight_max / volume_max (+ units)
config.vehicles.defaults.capacity       →  same patch for all types in the lot
catalog (POST /vehicles)                →  weight, volume, consumption
omit on catalog                         →  wire has no max_weight / max_volume (scenario 29)
```

Scenarios **27** (catalog only), **28** (override beats catalog), **29** (catalog empty).

**Rebalance time** (separate chain):

```
config.rebalance.rebalance_by_time.min/max_time_minutes_per_route
  > config.vehicles.defaults.route.time_min/max (+ time_unit)
  > fleet run_profile.route.time_*
  > lot.route_limits.time_* (+ time_unit)
  > wire defaults (60 / 420 min)
```

Canonical pattern examples: **A → J** in `explore_wire_request_matrix.py` (`PRECEDENCE_PATTERNS`).

---

## Rebalance dimensions (`config.rebalance`)

Each dimension is an optional branch: `rebalance_by_volume`, `rebalance_by_size`,
`rebalance_by_weight`, `rebalance_by_distance`, `rebalance_by_time`.

Shape:

```jsonc
"rebalance": {
  "rebalance_by_volume": {
    "enabled": true,
    "min_volume_capacity_ratio_vehicle": 0.44,
    "max_volume_capacity_ratio_vehicle": 0.94
  },
  "rebalance_by_size": { "enabled": true },
  "rebalance_by_weight": {
    "enabled": true,
    "min_weight_capacity_ratio_vehicle": 0.42,
    "max_weight_capacity_ratio_vehicle": 0.88
  },
  "rebalance_by_distance": { "enabled": true },
  "rebalance_by_time": {
    "enabled": true,
    "min_time_minutes_per_route": 90
  }
}
```

### Wire defaults vs explicit config

| Situation | Wire behavior |
|-----------|---------------|
| **`config.rebalance` omitted** | Adapter uses `PlanRebalance` defaults: **size=true**, volume/weight/distance/time=**false** |
| **`config.rebalance` present** | Each branch: `{ enabled: true }` → **true**; `{ enabled: false }` → **false**; **branch omitted** → **false** (does not inherit global default size=true) |

So if you send a `rebalance` object, list every dimension you want **on**, or set
`enabled: false` explicitly to document intent (**24**–**26**).

Distance rebalance (**20**) only toggles the dimension; per-route km still come from
**fleet** `run_profile.route` (or lot overrides / `route_limits`).

### Flag coverage matrix (scenarios)

| Dimension | ON (wire true) | OFF implicit (omit block or branch) | OFF explicit `{ enabled: false }` |
|-----------|----------------|-------------------------------------|-----------------------------------|
| **volume** | **10**, **18** | **01**, **19**, **20**, **21**, most A–J | **24**, **26** |
| **size** | **01**, **10**, **20**, **21** | — (default true only if no rebalance block) | **25**, **26** |
| **weight** | **21** | default | **24** (volume off), **26** |
| **distance** | **20** | default | **26** |
| **time** | **15** | default | **26** |

**E2E:** `docker compose exec api python scripts/test_plan_flow.py --scenario 24 --wire-only`

---

## `POST /lots/{id}/plan` requirements

Besides rebalance/schedule/zone (the “product” lot surface), the adapter requires
**modern-shaped blobs** in `lot.config`:

| Field | Required | Valid shape (summary) |
|-------|----------|------------------------|
| `clustering` | Partial | `min_size_cluster` / `max_size_cluster` optional — **auto-computed** from deliveries ÷ fleet qty when omitted (legacy) |
| `routing` | Yes | Includes `nearby_threshold_m`, `service_time_min`, etc. |
| `settings` | Yes | Includes `preprocessing` block |

**Clustering auto fallback (legacy, same as pre-greenfield `POST /plan`):**

```
max_size_cluster = ceil(delivery_count / sum(fleet.qty))
min_size_cluster = floor(max_size_cluster / 2)
```

**Settings preprocessing batch fallback (legacy):**

```
preprocessing_batch_size = max_size_cluster × 3
```

(applies when `settings.preprocessing.preprocessing_batch_size` is omitted; uses the
**resolved** `max_size_cluster` after clustering auto-fill).

Explicit sizes in `config.clustering` always win. Legacy blobs with only `{min, max}` (no
`allow_subclustering_by_volume`) are accepted; missing flags use `PlanClustering` defaults
(scenario `12`).

Missing `routing` → **422**. Scenario `22` shows auto clustering; `12`/`22`/`23` show auto
batch size when preprocessing omits `preprocessing_batch_size`.

In E2E, `test_plan_flow.py` merges clustering/routing/settings from the DBO1 JSON
**only** for tuning scenarios (`10`, `12`, `14`–`15`, `20`–`23`) or when you pass
`--dbo1-tuning`. Other scenarios use **API-only** lot config (+ minimal routing/settings
for planning). In production, send tuning in `POST /lots` until a server-side template exists.

**Important:** `POST /plan` reads **`config_data` from the database** (authoritative).
`PATCH /lots` deep-merges partial `config` into existing `config_data` via
`merge_config_data()` in `models/lot_config.py`.

---

## Scenario catalog — HTTP flow per case

**E2E legend**

| Tag | Meaning |
|-----|---------|
| **E2E OK** | `test_plan_flow.py --scenario N --wire-only` (real API + wire preview) |
| **E2E 422** | `--expect-plan-status 422` for explicit error scenarios |
| **Local** | `explore_wire_request_matrix.py` only (no HTTP or no fleet) |

**Commands**

```bash
# Local matrix (no HTTP)
docker compose exec api python scripts/explore_wire_request_matrix.py --scenario 04

# E2E: API + fleet → lot → wire table
docker compose exec api python scripts/test_plan_flow.py --scenario 06 --wire-only

# E2E + optimizer
docker compose exec api python scripts/test_plan_flow.py --scenario 01 --post-plan

# List scenarios
docker compose exec api python scripts/test_plan_flow.py --list-scenarios
```

### Master table

| # | Scenario | Pattern | E2E | Endpoints that shape the wire | Main wire effect |
|---|----------|---------|-----|--------------------------------|------------------|
| 00 | `00_greenfield_vehicles_no_fleet` | — | Local | `POST /vehicles` | No wire; next step is fleet |
| 00b | `00b_greenfield_fleet_no_lot_yet` | A (partial) | Local* | `POST /vehicles`, `POST /fleets` | Vehicles from fleet profile; no lot/rebalance |
| 01 | `01_fleet_run_profile_only` | **A** | OK | fleet + lot (`rebalance`, `schedule`) | Stops/distance from **fleet**; rebalance/schedule from lot |
| 02 | `02_fleet_catalog_only_fallback_stops` | **B** | OK | fleet (id+qty only) + lot | Stops from **fallback** at plan time |
| 03 | `03_legacy_route_limits_global` | **C** | OK | catalog fleet + lot **`route_limits`** | Same stops/km on **all** types |
| 04 | `04_fleet_profile_lot_override_one_vehicle` | **D** | OK | fleet + `config.vehicles.overrides` | **v3** `stops_max=150` (fleet had 180) |
| 05 | `05_no_fleet_profile_lot_vehicle_overrides` | **E** | OK | catalog fleet + full overrides | Route/behavior from **config** only |
| 06 | `06_lot_defaults_patch_all_vehicles` | **F** | OK | fleet + `config.vehicles.defaults` | All types `stops_max=999` overrides fleet |
| 07 | `07_fleet_qty_zero_v1` | A+ | OK | fleet (v1 qty=0) + lot | **v1** in wire with `quantity: 0` |
| 08 | `08_override_only_wire_type_not_in_fleet` | ⚠ | OK | fleet without v1 + override v1 | v1 in wire qty=0; **anti-pattern** |
| 09 | `09_precedence_override_fleet_route_limits` | **G** | OK | fleet + `route_limits` + override v3 | v3 **150** > fleet 180 > RL 99 |
| 10 | `10_public_rebalance_schedule_zone` | public | OK | fleet A + rebalance + schedule + zone | Ratios 0.44/0.94; time from `start_at` |
| 11 | `11_internal_clustering_routing_settings` | passthrough | OK | lot clustering/routing/settings blobs | Optimizer tuning |
| 12 | `12_legacy_clustering_explicit_sizes` | legacy | OK | clustering `{68, 137}` + settings sin batch | batch **411** (= 137×3) |
| 22 | `22_clustering_auto_from_fleet` | legacy auto | OK | no `clustering` key | **68 / 137** + batch **411** |
| 23 | `23_preprocessing_batch_from_explicit_cluster` | legacy batch | OK | clustering 116/176 + settings sin batch | batch **528** (= 176×3) |
| 14 | `14_units_meters_distance_hours_rebalance` | units | OK | `route_limits` HOUR + defaults METER/MINUTE | km in wire; rebalance time 30–480 min |
| 15 | `15_rebalance_time_branch_wins` | rebalance | OK | defaults route time + `rebalance_by_time` | min **90** from rebalance, not 30 |
| 17 | `17_patch_fleet_after_lot` | **H** | OK | POST fleet + lot → **`PATCH /fleets`** | v3 qty **50**, stops_max **200** |
| 18 | `18_patch_lot_config_before_plan` | **I** | OK | POST lot → **`PATCH /lots`** | override v3 **155** + rebalance min **0.50** |
| 19 | `19_legacy_vehicle_limits_no_wire` | **J** | OK | POST lot **`vehicle_limits`** | Stored on lot; wire uses **catalog** |
| 20 | `20_rebalance_by_distance` | rebalance | OK | fleet A + `rebalance_by_distance` | Flag **true**; km from **fleet** route |
| 21 | `21_rebalance_by_weight` | rebalance | OK | fleet A + `rebalance_by_weight` + ratios | Flag **true**; ratios **0.42/0.88** in wire |
| 24 | `24_rebalance_volume_explicit_off_weight_on` | rebalance | OK | volume `{enabled:false}` + weight on | volume **false**, weight **true**, size **false** |
| 25 | `25_rebalance_size_explicit_off_volume_on` | rebalance | OK | size `{enabled:false}` + volume on | size **false**, volume **true** |
| 26 | `26_rebalance_all_flags_explicit_off` | rebalance | OK | five branches `{enabled:false}` | all rebalance flags **false** |
| 27 | `27_catalog_max_weight_volume` | capacity | OK | fleet A; lot sin `capacity` | `max_weight`/`max_volume` from **catalog** |
| 28 | `28_capacity_override_beats_catalog` | capacity | OK | `overrides[].capacity` on v3 | Override **beats** catalog; v2 unchanged |
| 29 | `29_catalog_no_volume_weight` | capacity | OK | catalog type sin volume/weight | Wire **omits** `max_volume`/`max_weight` |
| 30 | `30_rebalance_omitted_adapter_defaults` | rebalance | OK | lot **sin** `config.rebalance` | size **true**, volume/weight/distance/time **false** |
| 31 | `31_override_by_wire_type_name` | **D′** | OK | override `vehicle_id: "v3"` (name) | Same as 04 (`"67"`); v3 stops_max **150** |
| 32 | `32_rebalance_weight_enabled_wire_defaults` | rebalance | OK | `rebalance_by_weight: {enabled: true}` only | Ratios **0.01/0.95**; size **false** |
| 33 | `33_fleet_compact_qty_50` | **A** | OK | fleet COMPACT (12+38) + rebalance size on | qty **12/38**; stops still from run_profile |
| 34 | `34_fleet_wide_qty_70` | **A** | OK | fleet WIDE (22+48); auto clustering | qty **22/48**; `max_size_cluster` from **70** vehículos |
| 35 | `35_rebalance_time_enabled_wire_defaults` | rebalance | OK | `rebalance_by_time: {enabled: true}` only | min/max **60/420** min; size **false** |
| 36 | `36_rebalance_volume_enabled_wire_defaults` | rebalance | OK | `rebalance_by_volume: {enabled: true}` only | ratios **0.1/0.925**; total **0.99** server |

\* `00b`: E2E script always creates a lot; use `explore_wire_request_matrix.py --scenario 00b` for the partial preview.

---

## HTTP sequence by scenario

### 00 — Catalog only

```
POST /vehicles  (v1, v2, v3)
```

No `fleet_id`, no wire. Next: scenario `01` or `00b`.

### 00b — Fleet ready, no lot

```
POST /vehicles  (×3)
POST /fleets    → vehicles[].id, qty, route, behavior
```

Partial wire (vehicles only). Still need milestone, deliveries, `POST /lots`, `POST /plan`.

### 01 — Pattern A (recommended production)

```
POST /vehicles
POST /fleets    → full run_profile per type
POST /milestones
POST /deliveries/bulk
POST /lots      → config: rebalance, schedule, zone
                → config.clustering / routing / settings (required today)
POST /lots/{id}/plan
GET  /lots/{id}/plan
```

**Wire:** per-vehicle stops from fleet; rebalance/schedule from lot.

### 02 — Pattern B (fallback stops)

```
POST /fleets    → { id, qty } only (no route/behavior)
POST /lots      → no route_limits, no config.vehicles
POST /lots/{id}/plan
```

**Wire:** `deliveries_qty.min/max` from fallback (delivery count ÷ fleet qty).

### 03 — Pattern C (global `route_limits`)

```
POST /fleets    → catalog + qty
POST /lots      → route_limits: stops_min/max, length_min/max (+ units)
POST /lots/{id}/plan
```

**Wire:** same stops and km on every vehicle.

### 04 — Pattern D (single-vehicle override)

```
POST /fleets    → DBO1 run_profile
POST /lots      → config.vehicles.overrides: [{ vehicle_id: "67"|"v3", route: { stops_max: 150 } }]
POST /lots/{id}/plan
```

**Wire:** v3 max **150**; v1/v2 unchanged.

### 05 — Pattern E (overrides without fleet profile)

```
POST /fleets    → id + qty only (v2, v3)
POST /lots      → config.vehicles.overrides with full route+behavior per type
POST /lots/{id}/plan
```

**Wire:** all route/behavior from config (legacy E2E path).

### 06 — Pattern F (`defaults` for all types)

```
POST /fleets    → DBO1 run_profile
POST /lots      → config.vehicles.defaults.route.stops_max: 999
POST /lots/{id}/plan
```

**Wire:** every type `stops_max=999`; `stops_min` still from fleet.

### 07 — Zero quantity

```
POST /fleets    → v1 qty=0 with run_profile
POST /lots      → normal config
POST /lots/{id}/plan
```

**Wire:** v1 present with `quantity: 0`.

### 08 — Anti-pattern

```
POST /fleets    → no v1 (v2, v3 only)
POST /lots      → override v1 with route/behavior
POST /lots/{id}/plan
```

**Wire:** includes v1 qty=0. **Risk:** routes may not persist without a fleet link.

### 09 — Pattern G (triple precedence)

```
POST /fleets    → v3 stops_max 180
POST /lots      → route_limits.stops_max: 99
                → overrides v3 stops_max: 150
POST /lots/{id}/plan
```

**Wire:** v3 max **150** (override wins).

### 10 — Public rebalance + schedule

```
POST /fleets    → pattern A
POST /lots      → config.rebalance (ratios), schedule (start_at, time_windows), zone
POST /lots/{id}/plan
```

**Wire:** ratios and route start time; vehicles from fleet.

### 11 — Clustering / routing / settings passthrough

```
POST /lots      → config.clustering, .routing, .settings (full blobs)
POST /lots/{id}/plan
```

**Wire:** optimizer tuning; same vehicles as pattern A.

### 12 — Legacy clustering blob (explicit sizes)

```
POST /lots      → config.clustering { min: 68, max: 137 } without allow_subclustering_by_volume
POST /lots/{id}/plan   → 202
```

**Wire:** uses stored 68/137; `preprocessing_batch_size = 411` (137×3, legacy auto).

### 22 — Clustering auto from fleet + deliveries

```
POST /lots      → config without clustering (routing/settings required)
POST /lots/{id}/plan
```

**Wire:** `max_size_cluster = ceil(deliveries / fleet qty)`, `min = floor(max/2)`.
With DBO1 (8205 deliveries, 60 vehicles): **68 / 137** and `preprocessing_batch_size = 411`.

```bash
docker compose exec api python scripts/test_plan_flow.py --scenario 22 --wire-only
```

### 23 — Preprocessing batch from explicit cluster max

```
POST /lots      → config.clustering { max: 176 } + settings without preprocessing_batch_size
POST /lots/{id}/plan
```

**Wire:** explicit cluster sizes unchanged; `preprocessing_batch_size = 528` (176×3).

```bash
docker compose exec api python scripts/test_plan_flow.py --scenario 23 --wire-only
```

### 14 — Units

```
POST /fleets    → catalog
POST /lots      → route_limits time 1–7 HOUR
                → defaults route distance METER + time MINUTE
POST /lots/{id}/plan
```

**Wire:** `distance_limits` in km; rebalance minutes from config route.

### 15 — Rebalance time wins

```
POST /lots      → defaults.route.time_min: 30
                → rebalance.rebalance_by_time.min_time_minutes_per_route: 90
POST /lots/{id}/plan
```

**Wire:** `rebalance.min_time_minutes_per_route = 90`.

### 17 — Pattern H (`PATCH /fleets` after lot exists)

```
POST /vehicles
POST /fleets    → DBO1 run_profile (v3 max 180, qty 43)
POST /milestones
POST /deliveries/bulk
POST /lots      → standard config (no vehicle patches)
PATCH /fleets/{id}  → v3 qty 50, stops_max 200
POST /lots/{id}/plan
```

**Wire:** reads **updated fleet** from DB. `lot.config_data` is unchanged.

```bash
docker compose exec api python scripts/test_plan_flow.py --scenario 17 --wire-only
```

### 18 — Pattern I (`PATCH /lots` before plan)

```
POST /fleets    → pattern A
POST /lots      → rebalance min_volume 0.45 (no override yet)
PATCH /lots/{id}  → override v3 stops_max 155 + rebalance min 0.50
POST /lots/{id}/plan
```

**Wire:** partial `config` is **deep-merged** into `config_data`; override wins over fleet for v3.

```bash
docker compose exec api python scripts/test_plan_flow.py --scenario 18 --wire-only
```

### 19 — Pattern J (`vehicle_limits` legacy, no wire effect)

```
POST /fleets    → pattern A
POST /lots      → vehicle_limits: { volume_min, volume_max, capacity_min, capacity_max }
POST /lots/{id}/plan
```

**Wire:** `max_volume` / `max_weight` from **catalog** (`GET /vehicles`). Lot `vehicle_*`
columns are persisted but the adapter **does not** map them to the optimizer.

```bash
docker compose exec api python scripts/test_plan_flow.py --scenario 19 --wire-only
```

### 20 — Rebalance by distance

```
POST /fleets    → pattern A (v3 distance_max 350 km)
POST /lots      → config.rebalance.rebalance_by_distance: { enabled: true }
                → rebalance_by_size: { enabled: true } (prod-like companion)
POST /lots/{id}/plan
```

**Wire:** `rebalance.rebalance_by_distance = true`. Per-vehicle `distance_limits` still come from
fleet `run_profile.route`, not from the rebalance branch.

```bash
docker compose exec api python scripts/test_plan_flow.py --scenario 20 --wire-only
```

### 21 — Rebalance by weight

```
POST /fleets    → pattern A
POST /lots      → config.rebalance.rebalance_by_weight:
                    enabled: true
                    min_weight_capacity_ratio_vehicle: 0.42
                    max_weight_capacity_ratio_vehicle: 0.88
POST /lots/{id}/plan
```

**Wire:** `rebalance.rebalance_by_weight = true` plus the ratio fields above.

```bash
docker compose exec api python scripts/test_plan_flow.py --scenario 21 --wire-only
```

### 24 — Volume explicitly off, weight on

```
POST /fleets    → pattern A
POST /lots      → config.rebalance:
                    rebalance_by_volume: { enabled: false }
                    rebalance_by_weight: { enabled: true, min: 0.42, max: 0.88 }
POST /lots/{id}/plan
```

**Wire:** `rebalance_by_volume=false`, `rebalance_by_weight=true`, `rebalance_by_size=false`
(size is false because the rebalance block is present and size is omitted).

```bash
docker compose exec api python scripts/test_plan_flow.py --scenario 24 --wire-only
```

### 25 — Size explicitly off, volume on

```
POST /lots      → config.rebalance:
                    rebalance_by_volume: { enabled: true, min: 0.44, max: 0.94 }
                    rebalance_by_size: { enabled: false }
POST /lots/{id}/plan
```

**Wire:** `rebalance_by_size=false` (overrides the global default of size=true when no block).

```bash
docker compose exec api python scripts/test_plan_flow.py --scenario 25 --wire-only
```

### 26 — All rebalance dimensions off

```
POST /lots      → config.rebalance with all five branches { enabled: false }
POST /lots/{id}/plan
```

**Wire:** every `rebalance_by_*` flag **false**.

```bash
docker compose exec api python scripts/test_plan_flow.py --scenario 26 --wire-only
```

### 27 — Catalog volume/weight on wire

```
POST /vehicles  → volume + weight per type (e.g. v2: 3313071 cm3, 1000 kg)
POST /fleets    → pattern A (run_profile only — no capacity)
POST /lots      → sin config.vehicles.capacity ni vehicle_limits
POST /lots/{id}/plan
```

**Wire:** `vehicles[v2].max_volume` / `max_weight` from catalog. Scenario **19** covers the
same for `vehicle_limits` legacy (ignored); **27** asserts weight explicitly.

```bash
docker compose exec api python scripts/explore_wire_request_matrix.py --scenario 27 --strict
```

### 28 — Capacity override beats catalog

```
POST /fleets    → pattern A
POST /lots      → config.vehicles.overrides:
                    vehicle_id: "67"
                    capacity: { volume_max, volume_unit, weight_max, weight_unit }
POST /lots/{id}/plan
```

**Wire:** v3 uses override caps; v2 still reads catalog.

```bash
docker compose exec api python scripts/explore_wire_request_matrix.py --scenario 28 --strict
```

### 29 — Catalog without volume/weight

```
POST /vehicles  → type without volume/weight fields
POST /fleets    → qty only
POST /lots      → minimal config
POST /lots/{id}/plan
```

**Wire:** no `max_volume` / `max_weight` on that type.

```bash
docker compose exec api python scripts/explore_wire_request_matrix.py --scenario 29 --strict
```

### 30 — Rebalance omitted (adapter defaults)

```
POST /fleets    → pattern A
POST /lots      → sin config.rebalance (solo routing/settings internos para plan)
POST /lots/{id}/plan
```

**Wire:** `rebalance_by_size=true`; volume, weight, distance, time **false** (`PlanRebalance` default).

```bash
docker compose exec api python scripts/explore_wire_request_matrix.py --scenario 30 --strict
```

### 31 — Override by wire_type name (`v3`)

```
POST /fleets    → pattern A
POST /lots      → overrides[{ vehicle_id: "v3", route: { stops_max: 150 } }]
POST /lots/{id}/plan
```

**Wire:** same as scenario **04** (`vehicle_id: "67"`). Proves `_find_override` accepts catalog id **or** `name`.

```bash
docker compose exec api python scripts/explore_wire_request_matrix.py --scenario 31 --strict
```

### 32 — Weight rebalance enabled, default ratios

```
POST /fleets    → pattern A
POST /lots      → config.rebalance.rebalance_by_weight: { enabled: true }
POST /lots/{id}/plan
```

**Wire:** `rebalance_by_weight=true`, ratios **0.01/0.95**; `rebalance_by_size=false` (block present, size omitted).

```bash
docker compose exec api python scripts/explore_wire_request_matrix.py --scenario 32 --strict
```

### 33 — Fleet COMPACT (total 50)

```
POST /fleets    → v2 qty 12, v3 qty 38 (same run_profile as DBO1)
POST /lots      → pattern A + rebalance_by_size on
POST /lots/{id}/plan
```

**Wire:** quantities **12 / 38**; route limits unchanged (qty does not change stops_max).

```bash
docker compose exec api python scripts/explore_wire_request_matrix.py --scenario 33 --strict
```

### 34 — Fleet WIDE (total 70)

```
POST /fleets    → v2 qty 22, v3 qty 48
POST /lots      → minimal config (auto clustering)
POST /lots/{id}/plan
```

**Wire:** quantities **22 / 48**; auto `max_size_cluster` uses **v_sum = 70** (not 60).

```bash
docker compose exec api python scripts/explore_wire_request_matrix.py --scenario 34 --strict
```

### 35 — Time rebalance enabled, default minutes

```
POST /fleets    → pattern A
POST /lots      → config.rebalance.rebalance_by_time: { enabled: true }
POST /lots/{id}/plan
```

**Wire:** `rebalance_by_time=true`, **60 / 420** min (no min/max in request); `rebalance_by_size=false`.

```bash
docker compose exec api python scripts/explore_wire_request_matrix.py --scenario 35 --strict
```

### 36 — Volume rebalance enabled, default ratios

```
POST /fleets    → pattern A
POST /lots      → config.rebalance.rebalance_by_volume: { enabled: true }
POST /lots/{id}/plan
```

**Wire:** `rebalance_by_volume=true`, ratios **0.1 / 0.925**; `max_volume_capacity_ratio_total=0.99` (server).

```bash
docker compose exec api python scripts/explore_wire_request_matrix.py --scenario 36 --strict
```

---

## PATCH flows (quick reference)

Scenarios **`17`** and **`18`** are the E2E references.

| Endpoint | Behavior |
|----------|----------|
| **`PATCH /fleets/{id}`** | Updates `run_profile` and qty in DB. Existing lots keep their `config_data`; the **next** `POST /plan` reads the new fleet. Lot overrides still beat fleet. |
| **`PATCH /lots/{id}`** | Deep-merge of `config` into `config_data` (plus optional `route_limits`, `vehicle_limits`). Next plan uses the merged blob from DB. |

---

## Anti-patterns

| Pattern | Problem |
|---------|---------|
| Override for a type **not** in fleet | Wire possible; route persistence fragile (`08`) |
| All limits in `config.vehicles` with bare fleet | Works (legacy E2E) but duplicates data — prefer fleet `run_profile` |
| Legacy routing / settings | **422** on plan if missing modern shape |
| Omitting `clustering` sizes | Auto **68/137** for DBO1-scale lots (scenario `22`) |
| Relying only on OpenAPI `POST /lots` example | May omit required clustering/routing/settings |
| Expecting `vehicle_limits` to cap wire volume | Stored only; wire uses catalog (`19`) |

---

## `route` shape (fleet and lot.config)

Distance and time use **value + explicit unit**:

```jsonc
{
  "route": {
    "stops_min": 30,
    "stops_max": 180,
    "distance_min": 1,
    "distance_max": 350,
    "distance_unit": "KILOMETER",
    "time_min": 30,
    "time_max": 480,
    "time_unit": "MINUTE"
  }
}
```

Use `distance_min` / `distance_max` with `distance_unit`, and `time_min` / `time_max` with
`time_unit` (defaults: `KILOMETER`, `MINUTE` when omitted).

---

## Tools

| Tool | Role |
|------|------|
| `explore_wire_request_matrix.py` | Scenario catalog + simulated wire + input→wire validation |
| `test_plan_flow.py` | Same catalog over **real HTTP** + precedence table (fleet → lot → wire) |
| `tests/` (local) | Fine-grained regression (units, rebalance, persistence) |

**Scripts vs tests:** scripts teach flows and precedence; unit tests catch regressions
the matrix will not fail unless you run `--scenario`.

---

## Quick reference: where each concept lives

| Concept | API location |
|---------|--------------|
| Fleet composition | `POST /fleets` → `vehicles[].id`, `qty` |
| Operational defaults | `POST /fleets` → `vehicles[].route`, `behavior` |
| Run knobs | `POST /lots` → `config.rebalance`, `schedule`, `zone` |
| Per-lot vehicle patch | `POST /lots` or `PATCH /lots` → `config.vehicles` |
| Legacy global limits | `POST /lots` → `route_limits`, `vehicle_limits` |
| Plan | `POST /lots/{id}/plan` (no body) |
| Optimizer tuning | `POST /lots` → `config.clustering`, `routing`, `settings` |
