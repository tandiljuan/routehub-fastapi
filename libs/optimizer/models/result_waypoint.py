from pydantic import BaseModel
from .time_window import OptimizerTimeWindow

class ResultDimension(BaseModel):
    length: int | float | None = None
    width: int | float | None = None
    height: int | float | None = None

class ResultPackage(BaseModel):
    package_id: str
    weight_kg: int | float | None = None
    volume_cm3: int | float | None = None
    dimensions: ResultDimension | None = None
    time_window: OptimizerTimeWindow | None = None

class ResultWaypoint(BaseModel):
    order: int
    lat: float
    lng: float
    packages: list[ResultPackage] | None = None
    arrival_time: float | int | str | None = None
    address: str | None = None
    has_time_window: bool | None = None
    time_window: OptimizerTimeWindow | None = None
    subroute_number: int | None = None
