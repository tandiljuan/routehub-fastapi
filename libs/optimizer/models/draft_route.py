from pydantic import BaseModel
from .draft_waypoint import DraftWaypoint

class DraftRoute(BaseModel):
    route_id: str
    driver: str | None = None
    waypoints: list[DraftWaypoint]
