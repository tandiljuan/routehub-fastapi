from pydantic import BaseModel

class ResultTotal(BaseModel):
    total_routes: int | None = None
    total_points: int | None = None
    total_distance_km: int | float | None = None
    total_duration_min: int | None = None
    total_duration_sec: int | None = None
    total_packages: int | None = None
