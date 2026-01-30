from pydantic import BaseModel
from .result_waypoint import ResultWaypoint

class ResultRoute(BaseModel):
    route_id: str | None = None
    driver: str | None = None
    vehicle_type: str
    route_geometry: list[list[float]]
    optimized_waypoints: list[ResultWaypoint]
