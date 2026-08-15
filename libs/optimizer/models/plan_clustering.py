from pydantic import BaseModel

from libs.plan_engine_defaults import _DEFAULT_CLUSTERING as _C


class PlanClustering(BaseModel):
    """Typed optimizer clustering payload.

    Engine knobs come from ``config/engine_defaults.json``.
    ``min_size_cluster`` / ``max_size_cluster`` and ``force_split_clusters``
    are computed per plan. ``force_vehicles_fleet_match`` comes from the lot
    (False if omitted).
    """

    strategy: str = "clustering"
    size_cluster_tolerance: float = _C["size_cluster_tolerance"]
    min_size_cluster: int
    max_size_cluster: int
    allow_subclustering_by_volume: bool = _C["allow_subclustering_by_volume"]
    volume_divide_threshold: float = _C["volume_divide_threshold"]
    allow_subclustering_by_capacity: bool = _C["allow_subclustering_by_capacity"]
    capacity_divide_threshold: float = _C["capacity_divide_threshold"]
    force_vehicles_fleet_match: bool = False
    force_split_clusters: bool = False
