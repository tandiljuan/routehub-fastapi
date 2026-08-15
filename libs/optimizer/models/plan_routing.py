from pydantic import BaseModel

from libs.plan_engine_defaults import _DEFAULT_ROUTING as _R


class PlanRouting(BaseModel):
    """Typed optimizer routing payload.

    Engine knobs come from ``config/engine_defaults.json``. Overlay fields
    (schedule / client ETA) are omitted from the wire unless the lot set them.
    """

    api_type: str = _R["api_type"]
    weight_routes: str = _R["weight_routes"]
    rectify_final_routes: bool = _R["rectify_final_routes"]
    nearby_threshold_m: float = _R["nearby_threshold_m"]
    reorder_nearby_postprocessing: bool = _R["reorder_nearby_postprocessing"]
    reorder_nearby_max_penalty: float = _R["reorder_nearby_max_penalty"]
    distance_haversine_limit: int = _R["distance_haversine_limit"]
    distance_factor: float = _R["distance_factor"]
    use_graph_travel_time: bool = _R["use_graph_travel_time"]
    two_opt_fast_mode: bool = _R["two_opt_fast_mode"]
    two_opt_min_improvement_pct: float = _R["two_opt_min_improvement_pct"]
    two_opt_base_max_iterations: int = _R["two_opt_base_max_iterations"]
    two_opt_base_consecutive_limit: int = _R["two_opt_base_consecutive_limit"]
    two_opt_base_total_limit: int = _R["two_opt_base_total_limit"]
    optimize_time_windows: bool | None = None
    start_time_minutes_route: int | None = None
    service_time_min: float | None = None
    avg_speed_kph: float | None = None
    early_tolerance_min: float | None = None
    late_tolerance_min: float | None = None
