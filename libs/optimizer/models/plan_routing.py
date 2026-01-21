from pydantic import BaseModel

class PlanRouting(BaseModel):
    api_type: str = "igraph"
    weight_routes: str = "length"
    optimize_time_windows: bool = False
    rectify_final_routes: bool = True
    nearby_threshold_m: float = 50.0
    reorder_nearby_postprocessing: bool = True
    reorder_nearby_max_penalty: float = 1.15
    distance_haversine_limit: int = 50
    distance_factor: float = 1.55
    start_time_minutes_route: int = 720
    service_time_min: float = 2.2
    avg_speed_kph: float = 40.0
    early_tolerance_min: float = 5.0
    late_tolerance_min: float = 10.0
    use_graph_travel_time: bool = False
    two_opt_fast_mode: bool = True
    two_opt_min_improvement_pct: float = 0.0075
    two_opt_base_max_iterations: int = 50
    two_opt_base_consecutive_limit: int = 25
    two_opt_base_total_limit: int = 45
