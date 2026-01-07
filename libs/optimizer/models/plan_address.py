from pydantic import BaseModel
from .plan_package import PlanPackage

class PlanAddress(BaseModel):
    lat: float
    lng: float
    packages: list[PlanPackage]
