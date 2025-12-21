from pydantic import field_serializer
from sqlmodel import (
    Field,
    SQLModel,
)
from .company import Company
from .vehicle import VehicleResponse

class FleetBase(SQLModel):
    name: str

class FleetVehicleCreate(SQLModel):
    qty: int
    id: str

class FleetCreate(FleetBase):
    vehicles: list[FleetVehicleCreate]

class FleetVehicleResponse(VehicleResponse):
    qty: int

class FleetResponse(FleetCreate):
    id: str | int
    vehicles: list[FleetVehicleResponse]

    @field_serializer('id', when_used='json')
    def serialize_id_to_str(self, id: int):
        return str(id)

class Fleet(FleetBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    company_id: int = Field(foreign_key="company.id")
