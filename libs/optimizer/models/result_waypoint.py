from pydantic import BaseModel
from .plan_package import PackageTimeWindow

class ResultDimension(BaseModel):
    length: int | float | None = None
    width: int | float | None = None
    height: int | float | None = None

class ResultPackage(BaseModel):
    package_id: str
    weight_kg: int | float | None = None
    volume_cm3: int | float | None = None
    dimensions: ResultDimension | None = None
    time_window: PackageTimeWindow | None = None

class ResultWaypoint(BaseModel):
    order: int
    lat: float
    lng: float
    packages: list[ResultPackage] | None = None
