from pydantic import BaseModel


class PlanRouting(BaseModel):
    """Typed optimizer routing payload.

    Engine tuning is left unset so the optimizer applies its own defaults
    (route-optimizer-app src/helpers/engine_defaults.py); fields stay declared so
    PLAN_ROUTING_JSON overrides still reach the wire. Overlay fields (schedule /
    client ETA) are omitted from the wire unless the lot set them.
    """

    api_type: str | None = None
    weight_routes: str | None = None
    rectify_final_routes: bool | None = None
    nearby_threshold_m: float | None = None
    reorder_nearby_postprocessing: bool | None = None
    reorder_nearby_max_penalty: float | None = None
    distance_haversine_limit: int | None = None
    distance_factor: float | None = None
    use_graph_travel_time: bool | None = None
    # U-turns for the whole plan: "allow" | "no_uturn". A vehicle type (PlanVehicle.allow_uturns) or a
    # route overrides it in the optimizer; None is not sent and the engine default (ROUTE_UTURN_POLICY) applies.
    uturn_policy: str | None = None
    # "depot" | "last_stop" and each city in one pass (lot config routing); None is not sent: round trip, as always
    route_end: str | None = None
    route_end_point: dict[str, float] | None = None
    visit_zones_once: bool | None = None
    two_opt_fast_mode: bool | None = None
    two_opt_min_improvement_pct: float | None = None
    two_opt_base_max_iterations: int | None = None
    two_opt_base_consecutive_limit: int | None = None
    two_opt_base_total_limit: int | None = None
    optimize_time_windows: bool | None = None
    start_time_minutes_route: int | None = None
    service_time_min: float | None = None
    avg_speed_kph: float | None = None
    early_tolerance_min: float | None = None
    late_tolerance_min: float | None = None
