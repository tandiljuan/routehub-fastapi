from pydantic import BaseModel
from .result_waypoint import ResultWaypoint

class ResultRoute(BaseModel):
    route_id: str | None = None
    driver: str | None = None
    vehicle_type: str | None = None
    route_geometry: list[list[float]]
    optimized_waypoints: list[ResultWaypoint]
    distance_km: float | None = None
    duration_sec: float | None = None
    total_packages: int | None = None
    load_percentage: float | None = None
    route_volume_cm3: float | None = None
    executor_capacity_cm3: float | None = None
    avg_speed_kmh: float | None = None
    stops_per_hour: float | None = None
    duration_formatted: str | None = None
    duration_hours: float | None = None
    duration_minutes: float | None = None
    tw_stats: dict | None = None
