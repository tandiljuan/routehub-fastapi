"""Maps DeliveryLot + LotConfig to the optimizer wire models.

The adapter joins:
  - Vehicle catalog: volume, weight, consumption, engine
  - Fleet run_profile: qty, route, behavior per vehicle type
  - DeliveryLot legacy columns: route_stops_*, route_length_*, route_time_*
  - LotConfig: rebalance, schedule, clustering, routing, settings, optional vehicles.*

Precedence per vehicle field: overrides > defaults > fleet.run_profile > route_limits
> POST /plan fallback stops.

Planning requires lot.config.routing and .settings. Clustering min/max and
settings.preprocessing_batch_size fall back to legacy formulas when omitted.
Rebalance falls back to PlanRebalance defaults when omitted.
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
from libs.plan_engine_defaults import coerce_bool, dynamic_fleet_cluster_size_boost
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
    vehicle_id = str(vehicle.id)
    wire_type = getattr(vehicle, "name", None) or vehicle_id
    cfg = _resolve_vehicle_config(
        lot_config,
        vehicle_id,
        wire_type=wire_type,
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
        priority_vehicle=behavior.priority if behavior and behavior.priority is not None else priority,
        overflow_vehicle=(
            behavior.overflow_vehicle
            if behavior and behavior.overflow_vehicle is not None
            else False
        ),
    )


class LotPlanConfigError(ValueError):
    pass


class ClusteringConfigError(LotPlanConfigError):
    pass


class RoutingConfigError(LotPlanConfigError):
    pass


class SettingsConfigError(LotPlanConfigError):
    pass


def compute_cluster_sizes(a_sum: int, v_sum: int) -> tuple[int, int]:
    if v_sum <= 0:
        raise ClusteringConfigError(
            'cannot auto-compute clustering sizes without fleet vehicles (v_sum > 0)'
        )
    if a_sum <= 0:
        raise ClusteringConfigError(
            'cannot auto-compute clustering sizes without deliveries (a_sum > 0)'
        )
    max_size_cluster = math.ceil(a_sum / v_sum)
    min_size_cluster = math.floor(max_size_cluster / 2)
    return min_size_cluster, max_size_cluster


def scale_cluster_sizes_for_dynamic_fleet(
    min_size_cluster: int,
    max_size_cluster: int,
    *,
    delivery_count: int,
    boost: float | None = None,
) -> tuple[int, int]:
    multiplier = (
        boost
        if boost is not None
        else dynamic_fleet_cluster_size_boost(delivery_count)
    )
    if multiplier <= 1.0:
        return min_size_cluster, max_size_cluster
    return (
        math.ceil(min_size_cluster * multiplier),
        math.ceil(max_size_cluster * multiplier),
    )


def compute_preprocessing_batch_size(max_size_cluster: int) -> int:
    """Legacy fallback: preprocessing batch = max cluster size × 4."""
    return max_size_cluster * 4


def resolve_force_split_clusters(force_vehicles_fleet_match: bool) -> bool:
    """Full fleet: one cluster per vehicle. Dynamic fleet: allow splitting oversized clusters."""
    return not force_vehicles_fleet_match


def build_plan_clustering(
    *,
    engine_clustering: dict,
    a_sum: int | None = None,
    v_sum: int | None = None,
) -> PlanClustering:
    stored = dict(engine_clustering)
    if "force_vehicles_fleet_match" in stored:
        stored["force_vehicles_fleet_match"] = coerce_bool(
            stored["force_vehicles_fleet_match"]
        )
    force_fleet_match = stored.get("force_vehicles_fleet_match")
    has_counts = bool(a_sum and v_sum)

    if force_fleet_match is False and has_counts:
        base_min, base_max = compute_cluster_sizes(a_sum, v_sum)
        boost = dynamic_fleet_cluster_size_boost(a_sum)
        min_s, max_s = scale_cluster_sizes_for_dynamic_fleet(
            base_min,
            base_max,
            delivery_count=a_sum,
            boost=boost,
        )
        stored["min_size_cluster"] = min_s
        stored["max_size_cluster"] = max_s
        logger.info(
            "dynamic fleet clustering boost: deliveries=%s vehicles=%s "
            "base=%s/%s boosted=%s/%s multiplier=%.2f",
            a_sum,
            v_sum,
            base_min,
            base_max,
            min_s,
            max_s,
            boost,
        )
    elif (
        stored.get("min_size_cluster") is None or stored.get("max_size_cluster") is None
    ) and has_counts:
        min_s, max_s = compute_cluster_sizes(a_sum, v_sum)
        stored.setdefault("min_size_cluster", min_s)
        stored.setdefault("max_size_cluster", max_s)

    force_fleet_match = coerce_bool(stored.get("force_vehicles_fleet_match", False))
    stored["force_split_clusters"] = resolve_force_split_clusters(force_fleet_match)

    return PlanClustering.model_validate(stored)


def build_plan_settings(
    *,
    engine_settings: dict,
    max_size_cluster: int | None = None,
) -> PlanSettings:
    if not engine_settings:
        raise SettingsConfigError(
            'server engine settings are required for planning '
            '(preprocessing, hardware, ...)'
        )
    stored = dict(engine_settings)
    pre = dict(stored.get("preprocessing") or {})
    if pre.get("preprocessing_batch_size") is None:
        if max_size_cluster is None:
            raise SettingsConfigError(
                'preprocessing_batch_size missing and cannot auto-compute '
                'without resolved max_size_cluster'
            )
        pre["preprocessing_batch_size"] = compute_preprocessing_batch_size(max_size_cluster)
        if pre.get("enable_address_preprocessing") is None:
            pre["enable_address_preprocessing"] = True
        stored["preprocessing"] = pre
    return PlanSettings.model_validate(stored)


def build_plan_rebalance(lot_config: LotConfig, lot_db=None) -> PlanRebalance:
    fields = PlanRebalance().model_dump()
    src = lot_config.rebalance
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
                overrides.update(branch_fields)
        fields.update(overrides)
        fields["max_volume_capacity_ratio_total"] = PlanRebalance().max_volume_capacity_ratio_total

    time_branch = src.rebalance_by_time if src is not None else None
    branch_set_min = (
        time_branch is not None and time_branch.min_time_minutes_per_route is not None
    )
    branch_set_max = (
        time_branch is not None and time_branch.max_time_minutes_per_route is not None
    )
    tmin, tmax = _resolve_time_bounds(lot_config, lot_db)
    if not branch_set_min and tmin is not None:
        fields["min_time_minutes_per_route"] = tmin
    if not branch_set_max and tmax is not None:
        fields["max_time_minutes_per_route"] = tmax
    return PlanRebalance(**fields)


def _flag(branch) -> bool:
    return branch is not None and branch.enabled


def build_plan_routing(lot_config: LotConfig, *, engine_routing: dict) -> PlanRouting:
    stored = engine_routing
    if not stored:
        raise RoutingConfigError(
            'server engine routing is required for planning '
            '(nearby_threshold_m, service_time_min, ...)'
        )
    if _is_legacy_routing(stored):
        raise RoutingConfigError(
            'server routing config is legacy-shaped; include nearby_threshold_m '
            'and explicit routing fields'
        )

    kwargs = {k: v for k, v in stored.items() if v is not None}

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
    qty_by_type: dict[str, int] = {}
    vehicle_by_type: dict[str, object] = {}

    for link in fleet_links:
        wire_type = getattr(link.vehicle, "name", None) or str(link.vehicle.id)
        qty_by_type[wire_type] = link.quantity
        vehicle_by_type[wire_type] = link.vehicle

    overrides = (
        lot_config.vehicles.overrides
        if lot_config.vehicles and lot_config.vehicles.overrides
        else []
    )
    for ov in overrides:
        if _override_belongs_to_fleet(ov, fleet_links):
            continue
        wire_type = ov.vehicle_id
        qty_by_type.setdefault(wire_type, 0)
        vehicle_by_type.setdefault(wire_type, _stub_vehicle(wire_type))

    fleet_cfg_by_type: dict[str, VehicleRunConfig] = {}
    run_profile_by_type: dict[str, object | None] = {}
    catalog_id_by_type: dict[str, str] = {}
    for link in fleet_links:
        wire_type = getattr(link.vehicle, "name", None) or str(link.vehicle.id)
        run_profile_by_type[wire_type] = getattr(link, "run_profile", None)
        fleet_cfg_by_type[wire_type] = _fleet_vehicle_config(link)
        catalog_id_by_type[wire_type] = str(link.vehicle.id)
    ordered = sorted(
        qty_by_type.keys(),
        key=lambda t: _vehicle_sort_key(
            lot_config,
            catalog_id_by_type.get(t, t),
            wire_type=t,
            fleet_cfg=fleet_cfg_by_type.get(t),
        ),
    )

    vehicles: list[PlanVehicle] = []
    for loop_priority, wire_type in enumerate(ordered, start=1):
        link = _FleetLinkStub(
            qty_by_type[wire_type],
            vehicle_by_type[wire_type],
            run_profile=run_profile_by_type.get(wire_type),
        )
        vehicles.append(build_plan_vehicle(
            link,
            lot_db,
            lot_config,
            loop_priority,
            fallback_stops_min=fallback_stops_min,
            fallback_stops_max=fallback_stops_max,
        ))
    return vehicles


def _is_legacy_routing(stored: dict) -> bool:
    return 'nearby_threshold_m' not in stored


def _vehicle_sort_key(
    lot_config: LotConfig,
    vehicle_id: str,
    *,
    wire_type: str | None = None,
    fleet_cfg: VehicleRunConfig | None = None,
) -> tuple:
    cfg = _resolve_vehicle_config(
        lot_config,
        vehicle_id,
        wire_type=wire_type,
        fleet_cfg=fleet_cfg,
    )
    if cfg.behavior and cfg.behavior.priority is not None:
        return (cfg.behavior.priority, wire_type)
    return (999, wire_type)


class _FleetLinkStub:
    __slots__ = ("quantity", "vehicle", "run_profile")

    def __init__(self, quantity: int, vehicle: object, run_profile=None):
        self.quantity = quantity
        self.vehicle = vehicle
        self.run_profile = run_profile


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
        wire = getattr(vehicle, "name", None)
        if wire:
            mapping[wire] = vid
            mapping[wire.lower()] = vid
            mapping[wire.upper()] = vid
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
    fleet_cfg: VehicleRunConfig | None = None,
) -> VehicleRunConfig:
    merged = fleet_cfg or VehicleRunConfig()
    vehicles = lot_config.vehicles
    if vehicles is None:
        return merged
    if vehicles.defaults is not None:
        merged = _merge_run_configs(merged, vehicles.defaults)
    specific = _find_override(vehicles.overrides, vehicle_id, wire_type=wire_type)
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


def _find_override(overrides, vehicle_id: str, *, wire_type: str | None = None):
    if not overrides:
        return None
    for item in overrides:
        if item.vehicle_id == vehicle_id:
            return item
        if wire_type and item.vehicle_id == wire_type:
            return item
    return None


def _override_belongs_to_fleet(override, fleet_links) -> bool:
    ov_id = override.vehicle_id
    for link in fleet_links:
        wire_type = getattr(link.vehicle, "name", None) or str(link.vehicle.id)
        if ov_id == str(link.vehicle.id) or ov_id == wire_type:
            return True
    return False


def _deliveries_qty(route, lot_db, fallback_min, fallback_max):
    cfg_min = route.stops_min if route else None
    cfg_max = route.stops_max if route else None
    smin = cfg_min or getattr(lot_db, "route_stops_min", None) or fallback_min
    smax = cfg_max or getattr(lot_db, "route_stops_max", None) or fallback_max
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


def _resolve_time_bounds(lot_config: LotConfig, lot_db) -> tuple[float | None, float | None]:
    route = None
    if lot_config.vehicles and lot_config.vehicles.defaults:
        route = lot_config.vehicles.defaults.route
    if route and route.time_min is not None:
        tmin = _to_minutes(route.time_min, route.time_unit or TimeUnit.MINUTE)
    elif lot_db is not None and getattr(lot_db, "route_time_min", None) is not None:
        tmin = _to_minutes(lot_db.route_time_min, getattr(lot_db, "route_time_unit", None))
    else:
        tmin = None
    if route and route.time_max is not None:
        tmax = _to_minutes(route.time_max, route.time_unit or TimeUnit.MINUTE)
    elif lot_db is not None and getattr(lot_db, "route_time_max", None) is not None:
        tmax = _to_minutes(lot_db.route_time_max, getattr(lot_db, "route_time_unit", None))
    else:
        tmax = None
    return tmin, tmax


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
