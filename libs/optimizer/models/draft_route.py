from pydantic import BaseModel
from .draft_waypoint import DraftWaypoint

class DraftRoute(BaseModel):
    route_id: str
    driver: str | None = None
    waypoints: list[DraftWaypoint]
    # The route's vehicle: its network ("bicycle") and whether it may turn around. None = plan/engine default.
    profile: str | None = None
    allow_uturns: bool | None = None
    # The route's clock (lot vehicles.defaults/overrides routing): overrides the plan's routing.* key. None = plan.
    service_time_min: float | None = None
    avg_speed_kph: float | None = None
    use_graph_travel_time: bool | None = None
    # Stop visited first ({"lat", "lng"} of one of the waypoints): the engine leaves the depot to it and orders the
    # rest (ROUTE_FIXED_FIRST_STOP). None = the engine picks the whole order.
    first_stop: dict[str, float] | None = None
