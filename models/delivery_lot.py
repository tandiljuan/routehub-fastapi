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
