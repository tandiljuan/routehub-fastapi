from pydantic import BaseModel

class DeliveriesQuantity(BaseModel):
    min: int | None = None
    max: int | None = None

class DistanceLimits(BaseModel):
    min_km: int | None = None
    max_km: int | None = None

class PlanVehicle(BaseModel):
    type: str
    quantity: int
    deliveries_qty: DeliveriesQuantity | None = None
    distance_limits: DistanceLimits | None = None
    priority_vehicle: int
    overflow_vehicle: bool | None = None
