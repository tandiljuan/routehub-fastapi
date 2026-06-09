from pydantic import BaseModel

class DeliveriesQuantity(BaseModel):
    min: int | None = None
    max: int | None = None

class DistanceLimits(BaseModel):
    min_km: int | None = None
    max_km: int | None = None

class MeasuredQuantity(BaseModel):
    value: float
    unit: str

class VehicleConsumption(BaseModel):
    value: float
    unit: str
    fuel_type: str

class PlanVehicle(BaseModel):
    type: str
    quantity: int
    deliveries_qty: DeliveriesQuantity | None = None
    distance_limits: DistanceLimits | None = None
    max_volume: MeasuredQuantity | None = None
    max_weight: MeasuredQuantity | None = None
    consumption: VehicleConsumption | None = None
    priority_vehicle: int
    overflow_vehicle: bool | None = None
