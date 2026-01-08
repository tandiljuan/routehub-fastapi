from sqlmodel import (
    Field,
    Relationship,
    SQLModel,
)
from .delivery_lot import DeliveryLot
from .driver import Driver
from .milestone import Milestone
from .vehicle import Vehicle

class DeliveryPlan(SQLModel, table=True):
    __tablename__ = "delivery_plan"

    id: int | None = Field(default=None, primary_key=True)
    delivery_lot_id: int = Field(foreign_key="delivery_lot.id")
    optimizer_id: str

    lot: DeliveryLot = Relationship()

class DeliveryPath(SQLModel, table=True):
    __tablename__ = "delivery_path"

    id: int | None = Field(default=None, primary_key=True)
    delivery_plan_id: int = Field(foreign_key="delivery_plan.id")
    milestone_id: int = Field(foreign_key="milestone.id")
    vehicle_id: int | None = Field(default=None, foreign_key="vehicle.id")
    driver_id: int | None = Field(default=None, foreign_key="driver.id")
