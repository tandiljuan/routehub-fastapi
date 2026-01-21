from pydantic import BaseModel

class DraftWaypoint(BaseModel):
    lat: float
    lng: float
    address: str | None = None
    packages: list = []
