from pydantic import BaseModel

class PlanClustering(BaseModel):
    strategy: str = "clustering"
    size_cluster_tolerance: float = 0.2
    min_size_cluster: int
    max_size_cluster: int
    allow_subclustering_by_capacity: bool = True
    capacity_divide_threshold: float = 1.5
    force_vehicles_fleet_match: bool = True
    force_split_clusters: bool = False
