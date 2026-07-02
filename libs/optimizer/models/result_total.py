from pydantic import BaseModel

class ResultTotal(BaseModel):
    total_routes: int | None = None
    total_points: int | None = None
    total_distance_km: int | float | None = None
    total_duration_min: int | None = None
    total_duration_sec: int | None = None
    total_packages: int | None = None
    execution_time_sec: float | None = None
    submitted_points: int | None = None
    unserved_points: int | None = None
    fleet_size: int | None = None
    fleet_capacity_total_cm3: float | None = None
    fleet_volume_used_cm3: float | None = None
    fleet_efficiency_percentage: float | None = None
    fleet_usage_percentage: float | None = None
    tw_total: int | None = None
    tw_inserted_ok: int | None = None
    tw_violations: int | None = None
    tw_fallback_violations: int | None = None
    tw_total_packages: int | None = None
    tw_violation_percentage: float | None = None
    tw_status: str | None = None
    rejection_summary: dict[str, int] | None = None
    rejected_deliveries: list[dict] | None = None
