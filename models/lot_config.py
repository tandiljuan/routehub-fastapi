from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import JSON
from sqlalchemy.types import TypeDecorator
from pydantic import ConfigDict
from sqlmodel import SQLModel

from .enum import LengthUnit, TimeUnit, VolumeUnit, WeightUnit

class VehicleCapacityConfig(SQLModel):
    volume_max: int | None = None
    volume_unit: VolumeUnit | None = None
    weight_max: int | None = None
    weight_unit: WeightUnit | None = None

class VehicleRouteConfig(SQLModel):
    stops_min: int | None = None
    stops_max: int | None = None
    distance_min: float | None = None
    distance_max: float | None = None
    distance_unit: LengthUnit | None = None
    time_min: float | None = None
    time_max: float | None = None
    time_unit: TimeUnit | None = None

class VehicleBehaviorConfig(SQLModel):
    priority: int | None = None
    overflow_vehicle: bool | None = None

class VehicleRunConfig(SQLModel):
    capacity: VehicleCapacityConfig | None = None
    route: VehicleRouteConfig | None = None
    behavior: VehicleBehaviorConfig | None = None

class FleetRunProfile(SQLModel):
    route: VehicleRouteConfig | None = None
    behavior: VehicleBehaviorConfig | None = None

class VehicleOverride(VehicleRunConfig):
    vehicle_id: str

class VehiclesConfig(SQLModel):
    defaults: VehicleRunConfig | None = None
    overrides: list[VehicleOverride] | None = None

class RebalanceByVolumeConfig(SQLModel):
    enabled: bool = True
    min_volume_capacity_ratio_vehicle_initial: float | None = None
    max_volume_capacity_ratio_vehicle_initial: float | None = None
    min_volume_capacity_ratio_vehicle: float | None = None
    max_volume_capacity_ratio_vehicle: float | None = None

class RebalanceBySizeConfig(SQLModel):
    enabled: bool = True

class RebalanceByWeightConfig(SQLModel):
    enabled: bool = True
    min_weight_capacity_ratio_vehicle: float | None = None
    max_weight_capacity_ratio_vehicle: float | None = None

class RebalanceByTimeConfig(SQLModel):
    enabled: bool = True
    min_time_minutes_per_route: float | None = None
    max_time_minutes_per_route: float | None = None

class RebalanceByDistanceConfig(SQLModel):
    enabled: bool = True

class RebalanceConfig(SQLModel):
    rebalance_by_volume: RebalanceByVolumeConfig | None = None
    rebalance_by_size: RebalanceBySizeConfig | None = None
    rebalance_by_weight: RebalanceByWeightConfig | None = None
    rebalance_by_time: RebalanceByTimeConfig | None = None
    rebalance_by_distance: RebalanceByDistanceConfig | None = None

class TimeWindowsConfig(SQLModel):
    early_tolerance_min: float | None = None
    late_tolerance_min: float | None = None

class ScheduleConfig(SQLModel):
    start_at: datetime | None = None
    respect_delivery_windows: bool | None = None
    time_windows: TimeWindowsConfig | None = None

class ClusteringConfig(SQLModel):
    """Client-editable clustering flags (server-owned keys stay in plan_engine_defaults)."""

    force_vehicles_fleet_match: bool | None = None

class LotConfig(SQLModel):
    model_config = ConfigDict(extra="ignore")

    vehicles: VehiclesConfig | None = None
    rebalance: RebalanceConfig | None = None
    schedule: ScheduleConfig | None = None
    clustering: ClusteringConfig | None = None
    zone: str | None = None

    def plan_date(self, fallback: date | None = None) -> str:
        if self.schedule and self.schedule.start_at:
            return as_utc(self.schedule.start_at).date().isoformat()
        return (fallback or date.today()).isoformat()

class LotConfigJSON(TypeDecorator):
    impl = JSON
    cache_ok = True

    def process_bind_param(self, value: Any, dialect) -> dict | None:
        if value is None:
            return None
        if isinstance(value, LotConfig):
            return value.model_dump(mode="json")
        if isinstance(value, dict):
            return config_to_lot_config(value).model_dump(mode="json")
        return LotConfig.model_validate(value).model_dump(mode="json")

    def process_result_value(self, value: Any, dialect) -> LotConfig | None:
        if value is None:
            return None
        return LotConfig.model_validate(value)

class FleetRunProfileJSON(TypeDecorator):
    impl = JSON
    cache_ok = True

    def process_bind_param(self, value: Any, dialect) -> dict | None:
        if value is None:
            return None
        if isinstance(value, FleetRunProfile):
            return value.model_dump(mode="json", exclude_none=True) or None
        return FleetRunProfile.model_validate(value).model_dump(mode="json", exclude_none=True) or None

    def process_result_value(self, value: Any, dialect) -> FleetRunProfile | None:
        if value is None:
            return None
        return FleetRunProfile.model_validate(value)

def config_to_lot_config(config: Any) -> LotConfig | None:
    if config is None:
        return None
    if isinstance(config, LotConfig):
        return config
    if isinstance(config, dict):
        from libs.plan_engine_defaults import strip_engine_keys_from_config

        config = strip_engine_keys_from_config(config)
    return LotConfig.model_validate(config)

def merge_lot_config(
    base: LotConfig | None,
    overlay: LotConfig | None,
) -> LotConfig | None:
    if overlay is None:
        return base
    merged = merge_config_data(
        base.model_dump(mode="json") if base else None,
        overlay.model_dump(mode="json"),
    )
    return LotConfig.model_validate(merged) if merged else None

def merge_config_data(base: dict | None, overlay: dict | None) -> dict | None:
    if overlay is None:
        return base
    if not base:
        return {k: v for k, v in overlay.items() if v is not None}
    out = dict(base)
    for key, val in overlay.items():
        if val is None:
            continue
        if key in out and isinstance(out[key], dict) and isinstance(val, dict):
            out[key] = merge_config_data(out[key], val)
        else:
            out[key] = val
    return out

def as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)