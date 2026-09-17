from pydantic import BaseModel


class PlanClustering(BaseModel):
    """Typed optimizer clustering payload.

    Tuning, cluster sizes and ``force_split_clusters`` are left unset so the optimizer
    applies its own defaults (route-optimizer-app src/helpers/engine_defaults.py).
    Fields stay declared so PLAN_CLUSTERING_JSON overrides still reach the wire.
    ``force_vehicles_fleet_match`` comes from the lot (False if omitted).
    """

    strategy: str = "clustering"
    size_cluster_tolerance: float | None = None
    min_size_cluster: int | None = None
    max_size_cluster: int | None = None
    allow_subclustering_by_volume: bool | None = None
    volume_divide_threshold: float | None = None
    allow_subclustering_by_capacity: bool | None = None
    capacity_divide_threshold: float | None = None
    force_vehicles_fleet_match: bool = False
    force_split_clusters: bool | None = None
