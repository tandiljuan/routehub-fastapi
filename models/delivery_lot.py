from sqlmodel import SQLModel
from .enum import (
    LengthUnit,
    TimeUnit,
)

class VehicleLimits(SQLModel):
    volume_min: int | None = None
    volume_max: int | None = None
    capacity_min: int | None = None
    capacity_max: int | None = None

class RouteLimits(SQLModel):
    stops_min: int | None = None
    stops_max: int | None = None
    length_min: int | None = None
    length_max: int | None = None
    length_unit: LengthUnit | None = None
    time_min: int | None = None
    time_max: int | None = None
    time_unit: TimeUnit | None = None

class DeliveryLotBase(SQLModel):
    vehicle_limits: VehicleLimits | None = None
    route_limits: RouteLimits | None = None

class DeliveryLotCreate(DeliveryLotBase):
    milestone_id: str
    deliveries: list[str]
    fleet_id: str
    drivers: list[str] | None = None
