from pydantic import field_serializer
from sqlmodel import (
    Column,
    Enum,
    Field,
    Relationship,
    SQLModel,
)
from .enum import (
    DeliveryLotState,
    LengthUnit,
    TimeUnit,
)
from .company import Company
from .delivery import (
    DeliveryResponse,
    Delivery,
)
from .driver import (
    DriverResponse,
    Driver,
)
from .fleet import (
    FleetResponse,
    Fleet,
)
from .milestone import (
    MilestoneResponse,
    Milestone,
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

class DeliveryLotResponse(DeliveryLotBase):
    id: str | int
    state: DeliveryLotState
    milestone: MilestoneResponse
    deliveries: list[DeliveryResponse]
    fleet: FleetResponse | None = None
    drivers: list[DriverResponse] | None = None

    @field_serializer('id', when_used='json')
    def serialize_id_to_str(self, id: int):
        return str(id)

class DeliveryLot(SQLModel, table=True):
    __tablename__ = "delivery_lot"

    id: int | None = Field(default=None, primary_key=True)
    company_id: int = Field(foreign_key="company.id")
    state: DeliveryLotState = Field(sa_column=Column(Enum(DeliveryLotState)), default=DeliveryLotState.UNPROCESSED)
    milestone_id: int | None = Field(default=None, foreign_key="milestone.id")
    fleet_id: int | None = Field(default=None, foreign_key="fleet.id")
    vehicle_volume_min: int | None = Field(default=None)
    vehicle_volume_max: int | None = Field(default=None)
    vehicle_capacity_min: int | None = Field(default=None)
    vehicle_capacity_max: int | None = Field(default=None)
    route_stops_min: int | None = Field(default=None)
    route_stops_max: int | None = Field(default=None)
    route_length_min: int | None = Field(default=None)
    route_length_max: int | None = Field(default=None)
    route_length_unit: LengthUnit | None = Field(default=None, sa_column=Column(Enum(LengthUnit)))
    route_time_min: int | None = Field(default=None)
    route_time_max: int | None = Field(default=None)
    route_time_unit: TimeUnit | None = Field(default=None, sa_column=Column(Enum(TimeUnit)))

    milestone: Milestone | None = Relationship()
    fleet: Fleet | None = Relationship()
    deliveries: list["DeliveryLotDelivery"] = Relationship(back_populates="lot", passive_deletes="all")
    drivers: list["DeliveryLotDriver"] = Relationship(back_populates="lot", passive_deletes="all")

    def normalize_submitted_dict(lot: dict) -> dict:
        # Parse IDs
        if lot.get("company_id", False):
            lot["company_id"] = int(lot["company_id"])
        if lot.get("milestone_id", False):
            lot["milestone_id"] = int(lot["milestone_id"])
        if lot.get("fleet_id", False):
            lot["fleet_id"] = int(lot["fleet_id"])
        # Set vehicle limits values
        if lot.get("vehicle_limits", False):
            vl = lot["vehicle_limits"]
            if vl.get("volume_min", False):
                lot["vehicle_volume_min"] = vl["volume_min"]
            if vl.get("volume_max", False):
                lot["vehicle_volume_max"] = vl["volume_max"]
            if vl.get("capacity_min", False):
                lot["vehicle_capacity_min"] = vl["capacity_min"]
            if vl.get("capacity_max", False):
                lot["vehicle_capacity_max"] = vl["capacity_max"]
        # Set route limits values
        if lot.get("route_limits", False):
            rl = lot["route_limits"]
            if rl.get("stops_min", False):
                lot["route_stops_min"] = rl["stops_min"]
            if rl.get("stops_max", False):
                lot["route_stops_max"] = rl["stops_max"]
            if rl.get("length_min", False):
                lot["route_length_min"] = rl["length_min"]
            if rl.get("length_max", False):
                lot["route_length_max"] = rl["length_max"]
            if rl.get("length_unit", False):
                lot["route_length_unit"] = rl["length_unit"]
            if rl.get("time_min", False):
                lot["route_time_min"] = rl["time_min"]
            if rl.get("time_max", False):
                lot["route_time_max"] = rl["time_max"]
            if rl.get("time_unit", False):
                lot["route_time_unit"] = rl["time_unit"]
        # Return sanitized dictionary
        return lot

class DeliveryLotDelivery(SQLModel, table=True):
    __tablename__ = "delivery_lot_delivery"

    delivery_lot_id: int | None = Field(default=None, foreign_key="delivery_lot.id", primary_key=True)
    delivery_id: int | None = Field(default=None, foreign_key="delivery.id", primary_key=True)

    lot: DeliveryLot = Relationship(back_populates="deliveries")
    delivery: Delivery = Relationship()

class DeliveryLotDriver(SQLModel, table=True):
    __tablename__ = "delivery_lot_driver"

    delivery_lot_id: int | None = Field(default=None, foreign_key="delivery_lot.id", primary_key=True)
    driver_id: int | None = Field(default=None, foreign_key="driver.id", primary_key=True)

    lot: DeliveryLot = Relationship(back_populates="drivers")
    driver: Driver = Relationship()
