"""Maps DeliveryLot + LotConfig to the optimizer wire models.

The adapter joins:
  - Vehicle catalog: volume, weight, consumption, engine
  - Fleet run_profile: qty, route, behavior per fleet-vehicle instance
  - DeliveryLot legacy columns: route_stops_*, route_length_*, route_time_*
  - LotConfig: rebalance, schedule, clustering, routing, settings, optional vehicles.*

Precedence per vehicle field: overrides > defaults > fleet.run_profile > route_limits
> POST /plan fallback stops.

Duration rebalance bounds: lot route_time_* (Duration card) > rebalance_by_time
min/max > fleet vehicles.defaults.route > PlanRebalance 60/420. 0 is a valid min.
A stale time-branch 360 (6h fleet) must not replace lot 0/60.

Distance rebalance bounds: lot route_length_* (km) > rebalance_by_distance
min/max_distance_km_per_route > fleet vehicles.defaults.route. Optional; omit
when unset. Per-vehicle distance_limits still apply.

Engine tuning, cluster sizes, force_split_clusters and preprocessing_batch_size are not
sent: the optimizer computes them (route-optimizer-app src/helpers/engine_defaults.py).
Rebalance falls back to PlanRebalance defaults when omitted.

Stop band (shared by every channel, enforced by the engine in route-optimizer-app
src/helpers/stop_band.py): without a minimum the engine uses 50% of the maximum, and a minimum
keeps at least 10% under the maximum (min ≤ floor(max × 0.9)). RouteHub still validates the fleet
totals against the lot's addresses (±5%) when the plan is queued.
"""

import logging
import math

from models.enum import (
    LengthUnit,
    TimeUnit,
    VehicleConsumptionUnit,
    VehicleEngineType,
    VolumeUnit,
    WeightUnit,
)
from models.lot_config import (
    LotConfig,
    VehicleBehaviorConfig,
    VehicleCapacityConfig,
    VehicleRouteConfig,
    VehicleRunConfig,
    as_utc,
)
from libs.optimizer.models.plan_clustering import PlanClustering
from libs.plan_engine_defaults import coerce_bool
from libs.optimizer.models.plan_rebalance import PlanRebalance
from libs.optimizer.models.plan_routing import PlanRouting
from libs.optimizer.models.plan_settings import PlanSettings
from libs.optimizer.models.plan_vehicle import (
    DeliveriesQuantity,
    DistanceLimits,
    MeasuredQuantity,
    PlanVehicle,
    VehicleConsumption,
)

logger = logging.getLogger(__name__)

# Mirrors the engine's MIN_STOP_BAND_MARGIN (route-optimizer-app src/helpers/stop_band.py), which
# applies it; api-doc validate.ts and vepathos-mcp preflight_checks.py mirror it too.
MIN_STOP_BAND_MARGIN = 0.10

_VOLUME_WIRE_UNITS: dict[VolumeUnit, str] = {
    VolumeUnit.CUBIC_CENTIMETER: "cm3",
    VolumeUnit.CUBIC_METER: "m3",
    VolumeUnit.LITER: "l",
    VolumeUnit.CUBIC_INCH: "in3",
    VolumeUnit.CUBIC_FEET: "ft3",
    VolumeUnit.GALLON: "gal",
}

_WEIGHT_WIRE_UNITS: dict[WeightUnit, str] = {
    WeightUnit.GRAMS: "g",
    WeightUnit.KILOGRAMS: "kg",
    WeightUnit.OUNCES: "oz",
    WeightUnit.POUNDS: "lb",
}

_CONSUMPTION_WIRE_UNITS: dict[VehicleConsumptionUnit, str] = {
    VehicleConsumptionUnit.LITERS_PER_100KM: "l/100km",
    VehicleConsumptionUnit.KILOMETERS_PER_LITER: "km/l",
    VehicleConsumptionUnit.MILES_PER_GALLON: "mpg",
    VehicleConsumptionUnit.GALLONS_PER_MILE: "gpm",
}

_ENGINE_WIRE_FUEL: dict[VehicleEngineType, str] = {
    VehicleEngineType.GASOLINE: "GASOLINE",
    VehicleEngineType.DIESEL: "DIESEL",
    VehicleEngineType.CNG: "CNG",
    VehicleEngineType.ELECTRIC: "ELECTRIC",
    VehicleEngineType.HYBRID: "HYBRID",
    VehicleEngineType.MECHANIC: "MECHANIC",
}

_LENGTH_TO_KM: dict[LengthUnit, float] = {
    LengthUnit.CENTIMETER: 1e-5,
    LengthUnit.METER: 1e-3,
    LengthUnit.KILOMETER: 1.0,
    LengthUnit.INCH: 2.54e-5,
    LengthUnit.FEET: 3.048e-4,
    LengthUnit.MILE: 1.609344,
}

_TIME_TO_MINUTES: dict[TimeUnit, float] = {
    TimeUnit.SECOND: 1.0 / 60.0,
    TimeUnit.MINUTE: 1.0,
    TimeUnit.HOUR: 60.0,
}

def _to_km(value: int | float, unit: LengthUnit | None) -> float:
    factor = _LENGTH_TO_KM.get(unit, 1.0) if unit else 1.0
    return float(value) * factor


def _to_minutes(value: int | float, unit: TimeUnit | None) -> float:
    factor = _TIME_TO_MINUTES.get(unit, 1.0) if unit else 1.0
    return float(value) * factor


def build_plan_vehicle(
    fleet_link,
    lot_db,
    lot_config: LotConfig,
    priority: int,
    *,
    fallback_stops_min: int | None = None,
    fallback_stops_max: int | None = None,
) -> PlanVehicle:
    vehicle = fleet_link.vehicle
    catalog_id = getattr(fleet_link, "catalog_vehicle_id", None) or str(vehicle.id)
    catalog_name = getattr(vehicle, "name", None) or catalog_id
    wire_type = getattr(fleet_link, "wire_type", None) or catalog_name
    cfg = _resolve_vehicle_config(
        lot_config,
        catalog_id,
        wire_type=wire_type,
        catalog_name=catalog_name,
        fleet_cfg=_fleet_vehicle_config(fleet_link),
    )

    capacity = cfg.capacity
    route = cfg.route
    behavior = cfg.behavior

    return PlanVehicle(
        type=wire_type,
        quantity=fleet_link.quantity,
        deliveries_qty=_deliveries_qty(route, lot_db, fallback_stops_min, fallback_stops_max),
        distance_limits=_distance_limits(route, lot_db),
        max_volume=_max_volume(capacity, vehicle),
        max_weight=_max_weight(capacity, vehicle),
        consumption=_consumption(vehicle),
        # `priority` is always the final unique wire rank (materialized in build_plan_vehicles).
        priority_vehicle=priority,
        overflow_vehicle=(
            behavior.overflow_vehicle
            if behavior and behavior.overflow_vehicle is not None
            else False
        ),
    )


class LotPlanConfigError(ValueError):
    pass


def build_plan_clustering(*, engine_clustering: dict) -> PlanClustering:
    stored = dict(engine_clustering)
    if "force_vehicles_fleet_match" in stored:
        stored["force_vehicles_fleet_match"] = coerce_bool(
            stored["force_vehicles_fleet_match"]
        )
    return PlanClustering.model_validate(stored)


def build_plan_settings(*, engine_settings: dict) -> PlanSettings:
    return PlanSettings.model_validate(dict(engine_settings or {}))


def _first_bound(*values) -> float | None:
    """First bound that was actually set. 0 is valid; only None is missing."""
    for value in values:
        if value is not None:
            return value
    return None


def build_plan_rebalance(lot_config: LotConfig, lot_db=None) -> PlanRebalance:
    fields = PlanRebalance().model_dump()
    src = lot_config.rebalance
    time_branch = src.rebalance_by_time if src is not None else None
    if src is not None:
        overrides = {
            "rebalance_by_volume": _flag(src.rebalance_by_volume),
            "rebalance_by_size": _flag(src.rebalance_by_size),
            "rebalance_by_weight": _flag(src.rebalance_by_weight),
            "rebalance_by_time": _flag(src.rebalance_by_time),
            "rebalance_by_distance": _flag(src.rebalance_by_distance),
        }
        for branch in (src.rebalance_by_volume, src.rebalance_by_weight, src.rebalance_by_time):
            if branch is not None:
                branch_fields = branch.model_dump(exclude_none=True, exclude={"enabled"})
                branch_fields.pop("max_volume_capacity_ratio_total", None)
                # Minutes are applied below (lot > branch > fleet > 60/420).
                # Dumping them here let a stale branch 360 beat Duration 0/60.
                if branch is time_branch:
                    branch_fields.pop("min_time_minutes_per_route", None)
                    branch_fields.pop("max_time_minutes_per_route", None)
                overrides.update(branch_fields)
        fields.update(overrides)
        fields["max_volume_capacity_ratio_total"] = PlanRebalance().max_volume_capacity_ratio_total

    lot_min, lot_max = _lot_time_bounds(lot_db)
    fleet_min, fleet_max = _fleet_time_bounds(lot_config)
    branch_min = (
        time_branch.min_time_minutes_per_route if time_branch is not None else None
    )
    branch_max = (
        time_branch.max_time_minutes_per_route if time_branch is not None else None
    )
    tmin = _first_bound(lot_min, branch_min, fleet_min)
    tmax = _first_bound(lot_max, branch_max, fleet_max)
    if tmin is not None:
        fields["min_time_minutes_per_route"] = tmin
    if tmax is not None:
        fields["max_time_minutes_per_route"] = tmax

    dist_branch = src.rebalance_by_distance if src is not None else None
    lot_dmin, lot_dmax = _lot_distance_bounds_km(lot_db)
    fleet_dmin, fleet_dmax = _fleet_distance_bounds_km(lot_config)
    branch_dmin = (
        dist_branch.min_distance_km_per_route if dist_branch is not None else None
    )
    branch_dmax = (
        dist_branch.max_distance_km_per_route if dist_branch is not None else None
    )
    dmin = _first_bound(lot_dmin, branch_dmin, fleet_dmin)
    dmax = _first_bound(lot_dmax, branch_dmax, fleet_dmax)
    if dmin is not None:
        fields["min_distance_km_per_route"] = dmin
    if dmax is not None:
        fields["max_distance_km_per_route"] = dmax
    return PlanRebalance(**fields)


def _flag(branch) -> bool:
    return branch is not None and branch.enabled


def build_plan_routing(lot_config: LotConfig, *, engine_routing: dict) -> PlanRouting:
    kwargs = {k: v for k, v in (engine_routing or {}).items() if v is not None}

    # Client ETA / timing overrides (whitelist preserved on the lot).
    if lot_config.routing is not None:
        client_routing = lot_config.routing.model_dump(exclude_none=True)
        for key, val in client_routing.items():
            kwargs[key] = val

    if lot_config.schedule is not None:
        schedule = lot_config.schedule
        if schedule.respect_delivery_windows is not None:
            kwargs['optimize_time_windows'] = schedule.respect_delivery_windows
        if schedule.start_at is not None:
            dt = as_utc(schedule.start_at)
            kwargs['start_time_minutes_route'] = dt.hour * 60 + dt.minute
        if schedule.time_windows is not None:
            tw = schedule.time_windows
            if tw.early_tolerance_min is not None:
                kwargs['early_tolerance_min'] = tw.early_tolerance_min
            if tw.late_tolerance_min is not None:
                kwargs['late_tolerance_min'] = tw.late_tolerance_min

    return PlanRouting.model_validate(kwargs)


def build_plan_vehicles(
    fleet_links,
    lot_db,
    lot_config: LotConfig,
    *,
    fallback_stops_min: int | None = None,
    fallback_stops_max: int | None = None,
) -> list[PlanVehicle]:
    entries: list[tuple[str, str, object, int, object | None]] = []
    seen_wire_types: dict[str, int] = {}

    for link in fleet_links:
        wire_type = _link_wire_type(link)
        catalog_id = str(link.vehicle.id)
        entry = (wire_type, catalog_id, link.vehicle, link.quantity, link)
        if wire_type in seen_wire_types:
            entries[seen_wire_types[wire_type]] = entry
        else:
            seen_wire_types[wire_type] = len(entries)
            entries.append(entry)

    overrides = (
        lot_config.vehicles.overrides
        if lot_config.vehicles and lot_config.vehicles.overrides
        else []
    )
    for ov in overrides:
        if _override_belongs_to_fleet(ov, fleet_links):
            continue
        if ov.vehicle_id in seen_wire_types:
            continue
        seen_wire_types[ov.vehicle_id] = len(entries)
        entries.append((ov.vehicle_id, ov.vehicle_id, _stub_vehicle(ov.vehicle_id), 0, None))

    ordered = sorted(
        entries,
        key=lambda e: _vehicle_sort_key(
            lot_config,
            e[1],
            wire_type=e[0],
            catalog_name=getattr(e[2], "name", None) or e[1],
            fleet_cfg=_fleet_vehicle_config(e[4]) if e[4] is not None else VehicleRunConfig(),
        ),
    )

    resolved_priorities: list[int | None] = []
    for wire_type, catalog_id, vehicle, _qty, link in ordered:
        cfg = _resolve_vehicle_config(
            lot_config,
            catalog_id,
            wire_type=wire_type,
            catalog_name=getattr(vehicle, "name", None) or catalog_id,
            fleet_cfg=_fleet_vehicle_config(link) if link is not None else VehicleRunConfig(),
        )
        pri = cfg.behavior.priority if cfg.behavior and cfg.behavior.priority is not None else None
        resolved_priorities.append(int(pri) if pri is not None else None)

    wire_priorities = _materialize_unique_priorities(resolved_priorities)

    vehicles: list[PlanVehicle] = []
    for (wire_type, catalog_id, vehicle, qty, link), priority in zip(
        ordered, wire_priorities, strict=True
    ):
        stub = _FleetLinkStub(
            qty,
            vehicle,
            run_profile=getattr(link, "run_profile", None) if link is not None else None,
            wire_type=wire_type,
            catalog_vehicle_id=catalog_id,
        )
        vehicles.append(build_plan_vehicle(
            stub,
            lot_db,
            lot_config,
            priority,
            fallback_stops_min=fallback_stops_min,
            fallback_stops_max=fallback_stops_max,
        ))
    return vehicles


def _materialize_unique_priorities(resolved: list[int | None]) -> list[int]:
    """
    Fill missing / duplicate behavior.priority values with unique ranks.

    UI shows missing priority as array-index+1, but the wire used to omit it;
    the previous loop_priority fallback then collided (e.g. bike=1, AMZ=3,
    van=None → van became 3). Keep unique explicit values; fill gaps with the
    smallest unused positive integers in sort order.
    """
    n = len(resolved)
    if n == 0:
        return []

    counts: dict[int, int] = {}
    for p in resolved:
        if p is not None:
            counts[p] = counts.get(p, 0) + 1

    result: list[int | None] = [None] * n
    used: set[int] = set()
    for i, p in enumerate(resolved):
        if p is not None and counts.get(p, 0) == 1:
            result[i] = int(p)
            used.add(int(p))

    next_free = 1
    for i in range(n):
        if result[i] is not None:
            continue
        while next_free in used:
            next_free += 1
        result[i] = next_free
        used.add(next_free)
        next_free += 1

    return [int(p) for p in result]  # type: ignore[arg-type]


def _link_wire_type(link) -> str:
    alias = getattr(link, "alias", None)
    if alias:
        return alias
    return getattr(link.vehicle, "name", None) or str(link.vehicle.id)


def _vehicle_sort_key(
    lot_config: LotConfig,
    vehicle_id: str,
    *,
    wire_type: str | None = None,
    catalog_name: str | None = None,
    fleet_cfg: VehicleRunConfig | None = None,
) -> tuple:
    cfg = _resolve_vehicle_config(
        lot_config,
        vehicle_id,
        wire_type=wire_type,
        catalog_name=catalog_name,
        fleet_cfg=fleet_cfg,
    )
    if cfg.behavior and cfg.behavior.priority is not None:
        return (cfg.behavior.priority, wire_type)
    return (999, wire_type)


class _FleetLinkStub:
    __slots__ = ("quantity", "vehicle", "run_profile", "wire_type", "catalog_vehicle_id", "alias")

    def __init__(self, quantity: int, vehicle: object, run_profile=None, wire_type=None, catalog_vehicle_id=None):
        self.quantity = quantity
        self.vehicle = vehicle
        self.run_profile = run_profile
        self.wire_type = wire_type
        self.catalog_vehicle_id = catalog_vehicle_id
        self.alias = wire_type


def _stub_vehicle(wire_type: str):
    return type("VehicleStub", (), {
        "id": wire_type,
        "name": wire_type,
        "volume": None,
        "volume_unit": None,
        "weight": None,
        "weight_unit": None,
        "consumption": None,
        "consumption_unit": None,
        "engine_type": None,
    })()


def build_wire_type_to_vehicle_id_map(fleet_links) -> dict[str, int]:
    mapping: dict[str, int] = {}
    for link in fleet_links:
        vehicle = link.vehicle
        vid = int(vehicle.id)
        mapping[str(vid)] = vid
        for candidate in (
            getattr(vehicle, "name", None),
            getattr(link, "alias", None),
        ):
            if not candidate:
                continue
            mapping[candidate] = vid
            mapping[candidate.lower()] = vid
            mapping[candidate.upper()] = vid
    return mapping


def resolve_vehicle_id(wire_map: dict[str, int], vehicle_type: str | None) -> int | None:
    if not vehicle_type:
        return None
    if vehicle_type in wire_map:
        return wire_map[vehicle_type]
    lower = vehicle_type.lower()
    if lower in wire_map:
        return wire_map[lower]
    if vehicle_type.isdigit():
        return int(vehicle_type)
    raise ValueError(f"Unknown optimizer vehicle_type for catalog lookup: {vehicle_type!r}")


def _fleet_vehicle_config(fleet_link) -> VehicleRunConfig:
    profile = getattr(fleet_link, "run_profile", None)
    if not profile:
        return VehicleRunConfig()
    return VehicleRunConfig.model_validate(profile)


def _merge_run_configs(base: VehicleRunConfig, override: VehicleRunConfig) -> VehicleRunConfig:
    return VehicleRunConfig(
        capacity=_merge_branch(VehicleCapacityConfig, base.capacity, override.capacity),
        route=_merge_branch(VehicleRouteConfig, base.route, override.route),
        behavior=_merge_branch(VehicleBehaviorConfig, base.behavior, override.behavior),
    )


def _resolve_vehicle_config(
    lot_config: LotConfig,
    vehicle_id: str,
    *,
    wire_type: str | None = None,
    catalog_name: str | None = None,
    fleet_cfg: VehicleRunConfig | None = None,
) -> VehicleRunConfig:
    merged = fleet_cfg or VehicleRunConfig()
    vehicles = lot_config.vehicles
    if vehicles is None:
        return merged
    if vehicles.defaults is not None:
        merged = _merge_run_configs(merged, vehicles.defaults)
    specific = _find_override(
        vehicles.overrides,
        vehicle_id,
        wire_type=wire_type,
        catalog_name=catalog_name,
    )
    if specific is not None:
        merged = _merge_run_configs(merged, specific)
    return merged


def _merge_branch(cls, base, override):
    if base is None and override is None:
        return None
    if base is None:
        return override
    if override is None:
        return base
    merged = base.model_dump(exclude_unset=True)
    merged.update(override.model_dump(exclude_unset=True))
    return cls.model_validate(merged)


def _find_override(
    overrides,
    vehicle_id: str,
    *,
    wire_type: str | None = None,
    catalog_name: str | None = None,
):
    if not overrides:
        return None
    per_instance = None
    per_catalog = None
    for item in overrides:
        oid = item.vehicle_id
        if wire_type and oid == wire_type:
            per_instance = item
            continue
        if oid == vehicle_id:
            per_catalog = per_catalog or item
            continue
        if catalog_name and oid == catalog_name:
            per_catalog = per_catalog or item
    return per_instance or per_catalog


def _override_belongs_to_fleet(override, fleet_links) -> bool:
    ov_id = override.vehicle_id
    for link in fleet_links:
        catalog_name = getattr(link.vehicle, "name", None) or str(link.vehicle.id)
        alias = getattr(link, "alias", None)
        if ov_id == str(link.vehicle.id) or ov_id == catalog_name or ov_id == alias:
            return True
    return False


def _deliveries_qty(route, lot_db, fallback_min, fallback_max):
    cfg_min = route.stops_min if route else None
    cfg_max = route.stops_max if route else None
    smin = cfg_min or getattr(lot_db, "route_stops_min", None) or fallback_min
    smax = cfg_max or getattr(lot_db, "route_stops_max", None) or fallback_max
    ceiling = math.floor(smax * (1 - MIN_STOP_BAND_MARGIN)) if smax is not None else None
    if smin is not None and ceiling is not None and smin > ceiling:
        logging.getLogger(__name__).warning(
            "stop_band_margin: min_stops=%s above floor(max×%s)=%s (max=%s); the engine lowers it",
            smin,
            1 - MIN_STOP_BAND_MARGIN,
            ceiling,
            smax,
        )
    return DeliveriesQuantity(min=smin, max=smax) if (smin or smax) else None


def _distance_limits(route, lot_db):
    if route and route.distance_min is not None:
        dmin = _to_km(route.distance_min, route.distance_unit or LengthUnit.KILOMETER)
    elif getattr(lot_db, "route_length_min", None) is not None:
        dmin = _to_km(lot_db.route_length_min, getattr(lot_db, "route_length_unit", None))
    else:
        dmin = None
    if route and route.distance_max is not None:
        dmax = _to_km(route.distance_max, route.distance_unit or LengthUnit.KILOMETER)
    elif getattr(lot_db, "route_length_max", None) is not None:
        dmax = _to_km(lot_db.route_length_max, getattr(lot_db, "route_length_unit", None))
    else:
        dmax = None
    if dmin is not None:
        dmin = int(round(dmin))
    if dmax is not None:
        dmax = int(round(dmax))
    return DistanceLimits(min_km=dmin, max_km=dmax) if (dmin is not None or dmax is not None) else None


def _lot_time_bounds(lot_db) -> tuple[float | None, float | None]:
    """Duration / POST /lots `route_limits.time_*`. 0 is a valid min."""
    tmin = None
    tmax = None
    if lot_db is not None:
        if getattr(lot_db, "route_time_min", None) is not None:
            tmin = _to_minutes(lot_db.route_time_min, getattr(lot_db, "route_time_unit", None))
        if getattr(lot_db, "route_time_max", None) is not None:
            tmax = _to_minutes(lot_db.route_time_max, getattr(lot_db, "route_time_unit", None))
    return tmin, tmax


def _fleet_time_bounds(lot_config: LotConfig) -> tuple[float | None, float | None]:
    """vehicles.defaults.route — catalog / 6h fleet profile. Not a user Duration cap."""
    tmin = None
    tmax = None
    route = None
    if lot_config.vehicles and lot_config.vehicles.defaults:
        route = lot_config.vehicles.defaults.route
    if route is not None and route.time_min is not None:
        tmin = _to_minutes(route.time_min, route.time_unit or TimeUnit.MINUTE)
    if route is not None and route.time_max is not None:
        tmax = _to_minutes(route.time_max, route.time_unit or TimeUnit.MINUTE)
    return tmin, tmax


def _resolve_time_bounds(lot_config: LotConfig, lot_db) -> tuple[float | None, float | None]:
    """Lot-level route_limits beat fleet catalog time_min/max.

    Duration card override → DeliveryLot.route_time_*. Fleet run_profile is
    only the fallback when the lot did not set a bound. 0 is a valid min.
    """
    tmin, tmax = _lot_time_bounds(lot_db)
    if tmin is not None and tmax is not None:
        return tmin, tmax
    fleet_min, fleet_max = _fleet_time_bounds(lot_config)
    return _first_bound(tmin, fleet_min), _first_bound(tmax, fleet_max)


def _lot_distance_bounds_km(lot_db) -> tuple[float | None, float | None]:
    """POST /lots `route_limits.length_*` converted to km. Optional."""
    dmin = None
    dmax = None
    if lot_db is not None:
        unit = getattr(lot_db, "route_length_unit", None)
        if getattr(lot_db, "route_length_min", None) is not None:
            dmin = _to_km(lot_db.route_length_min, unit)
        if getattr(lot_db, "route_length_max", None) is not None:
            dmax = _to_km(lot_db.route_length_max, unit)
    return dmin, dmax


def _fleet_distance_bounds_km(lot_config: LotConfig) -> tuple[float | None, float | None]:
    """vehicles.defaults.route distance — catalog km, not a required cap."""
    dmin = None
    dmax = None
    route = None
    if lot_config.vehicles and lot_config.vehicles.defaults:
        route = lot_config.vehicles.defaults.route
    if route is not None and route.distance_min is not None:
        dmin = _to_km(route.distance_min, route.distance_unit or LengthUnit.KILOMETER)
    if route is not None and route.distance_max is not None:
        dmax = _to_km(route.distance_max, route.distance_unit or LengthUnit.KILOMETER)
    return dmin, dmax


def _max_volume(capacity, vehicle):
    if capacity and capacity.volume_max is not None and capacity.volume_unit:
        return MeasuredQuantity(
            value=float(capacity.volume_max),
            unit=_VOLUME_WIRE_UNITS.get(capacity.volume_unit, capacity.volume_unit.value.lower()),
        )
    if getattr(vehicle, "volume", None) is not None and getattr(vehicle, "volume_unit", None):
        return MeasuredQuantity(
            value=float(vehicle.volume),
            unit=_VOLUME_WIRE_UNITS.get(vehicle.volume_unit, vehicle.volume_unit.value.lower()),
        )
    return None


def _max_weight(capacity, vehicle):
    if capacity and capacity.weight_max is not None and capacity.weight_unit:
        return MeasuredQuantity(
            value=float(capacity.weight_max),
            unit=_WEIGHT_WIRE_UNITS.get(capacity.weight_unit, capacity.weight_unit.value.lower()),
        )
    if getattr(vehicle, "weight", None) is not None and getattr(vehicle, "weight_unit", None):
        return MeasuredQuantity(
            value=float(vehicle.weight),
            unit=_WEIGHT_WIRE_UNITS.get(vehicle.weight_unit, vehicle.weight_unit.value.lower()),
        )
    return None


def _consumption(vehicle):
    if vehicle.consumption is None:
        return None
    unit = "l/100km"
    if vehicle.consumption_unit:
        unit = _CONSUMPTION_WIRE_UNITS.get(
            vehicle.consumption_unit, vehicle.consumption_unit.value.lower()
        )
    fuel_type = "GASOLINE"
    if vehicle.engine_type:
        fuel_type = _ENGINE_WIRE_FUEL.get(vehicle.engine_type, vehicle.engine_type.value)
    return VehicleConsumption(value=float(vehicle.consumption), unit=unit, fuel_type=fuel_type)
