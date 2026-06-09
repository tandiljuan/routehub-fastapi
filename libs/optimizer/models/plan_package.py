from pydantic import BaseModel

class PackageDimensions(BaseModel):
    length: float | None = None
    width: float | None = None
    height: float | None = None

class PackageTimeWindow(BaseModel):
    start: str
    end: str
    time_zone: str | None = None

class PlanPackage(BaseModel):
    package_id: str
    weight_kg: float | None = None
    dimensions: PackageDimensions | None = None
    time_window: PackageTimeWindow | None = None
    status: str | None = None
