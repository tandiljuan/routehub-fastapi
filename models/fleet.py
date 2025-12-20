from pydantic import field_serializer
from sqlmodel import SQLModel
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
