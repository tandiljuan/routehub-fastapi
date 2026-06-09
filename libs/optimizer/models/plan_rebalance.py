from pydantic import BaseModel

class PlanRebalance(BaseModel):
    rebalance_by_volume: bool = False
    rebalance_by_size: bool = True
    rebalance_by_weight: bool = False
    rebalance_by_distance: bool = False
    rebalance_by_time: bool = False

    min_volume_capacity_ratio_vehicle_initial: float = 0.4
    max_volume_capacity_ratio_vehicle_initial: float = 0.95
    min_volume_capacity_ratio_vehicle: float = 0.1
    max_volume_capacity_ratio_vehicle: float = 0.925
    max_volume_capacity_ratio_total: float = 0.99

    min_weight_capacity_ratio_vehicle: float = 0.01
    max_weight_capacity_ratio_vehicle: float = 0.95

    min_time_minutes_per_route: float = 60.0
    max_time_minutes_per_route: float = 420.0

    update_volume_capacity_vehicle: bool = False
    max_neighbors_per_cluster: int = 15

    rebalance_prepass_enabled: bool = True
    rebalance_prepass_max_iters: int = 1
    rebalance_prepass_max_moves_per_region: int = 60
