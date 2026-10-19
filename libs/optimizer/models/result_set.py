from pydantic import BaseModel
from .result_route import ResultRoute
from .result_total import ResultTotal

class ResultSet(BaseModel):
    session_id: str | None = None
    status: str | None = None
    routes: list[ResultRoute] | None = None
    totals: ResultTotal | None = None
    rejection_summary: dict[str, int] | None = None
    rejected_deliveries: list[dict] | None = None
    submitted_points: int | None = None
    unserved_points: int | None = None
    # Set by the engine on a session it could not route (status="failed"): the human
    # reason and a machine code ("area_too_large", "country_route_unavailable", or None).
    message: str | None = None
    error_code: str | None = None
