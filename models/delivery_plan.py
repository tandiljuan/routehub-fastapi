from sqlmodel import (
    Field,
    Relationship,
    SQLModel,
)
from .delivery import (
    Delivery,
    DeliveryResponse,
)
from .delivery_lot import DeliveryLot
from .driver import (
    Driver,
    DriverResponse,
)
from .milestone import (
    Milestone,
    MilestoneResponse,
)
from .vehicle import (
    Vehicle,
    VehicleResponse,
)

class RouteResponse(SQLModel):
    milestone: MilestoneResponse
    deliveries: list[DeliveryResponse]
    vehicle: VehicleResponse | None = None
    driver: DriverResponse | None = None

class DeliveryPlan(SQLModel, table=True):
    __tablename__ = "delivery_plan"

    id: int | None = Field(default=None, primary_key=True)
    delivery_lot_id: int = Field(foreign_key="delivery_lot.id")
    optimizer_id: str

    lot: DeliveryLot = Relationship()
    paths: list["DeliveryPath"] = Relationship(back_populates="plan", passive_deletes="all")

class DeliveryPath(SQLModel, table=True):
    __tablename__ = "delivery_path"

    id: int | None = Field(default=None, primary_key=True)
    delivery_plan_id: int = Field(foreign_key="delivery_plan.id")
    milestone_id: int = Field(foreign_key="milestone.id")
    vehicle_id: int | None = Field(default=None, foreign_key="vehicle.id")
    driver_id: int | None = Field(default=None, foreign_key="driver.id")

    plan: DeliveryPlan = Relationship()
    milestone: Milestone = Relationship()
    vehicle: Vehicle = Relationship()
    driver: Driver = Relationship()
    deliveries: list["DeliveryPathDelivery"] = Relationship(back_populates="path", passive_deletes="all")

class DeliveryPathDelivery(SQLModel, table=True):
    __tablename__ = "delivery_path_delivery"

    delivery_path_id: int | None = Field(default=None, foreign_key="delivery_path.id", primary_key=True)
    delivery_id: int | None = Field(default=None, foreign_key="delivery.id", primary_key=True)
    delivery_order: int

    path: DeliveryPath = Relationship(back_populates="deliveries")
    delivery: Delivery = Relationship()
