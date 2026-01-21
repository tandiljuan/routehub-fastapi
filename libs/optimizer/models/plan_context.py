from pydantic import BaseModel
from .plan_address import PlanAddress
from .plan_clustering import PlanClustering
from .plan_rebalance import PlanRebalance
from .plan_routing import PlanRouting
from .plan_settings import PlanSettings
from .plan_vehicle import PlanVehicle

class PlanContext(BaseModel):
    date: str
    time_slot: str = "00:00 - 23:59"
    origin_lat: float
    origin_lng: float
    tag: str
    zone: str = "MULTI"
    wait_for_response: bool = False
    vehicles: list[PlanVehicle]
    clustering: PlanClustering
    routing: PlanRouting
    rebalance: PlanRebalance
    settings: PlanSettings
    addresses: list[PlanAddress]
