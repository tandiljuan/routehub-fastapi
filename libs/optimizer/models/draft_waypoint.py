from pydantic import BaseModel

class DraftPackage(BaseModel):
    package_id: str

class DraftWaypoint(BaseModel):
    lat: float
    lng: float
    address: str | None = None
    packages: list[DraftPackage] = []
