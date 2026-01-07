from pydantic import BaseModel

class PlanRebalance(BaseModel):
    rebalance_by_volume: bool = False
    rebalance_by_size: bool = True
    rebalance_by_weight: bool = False
    rebalance_by_distance: bool = False
    rebalance_by_time: bool = False
