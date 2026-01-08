from sqlmodel import (
    Field,
    SQLModel,
)
from .delivery_lot import DeliveryLot

class DeliveryPlan(SQLModel, table=True):
    __tablename__ = "delivery_plan"

    id: int | None = Field(default=None, primary_key=True)
    delivery_lot_id: int = Field(foreign_key="delivery_lot.id")
    optimizer_id: str
