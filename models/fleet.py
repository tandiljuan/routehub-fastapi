from pydantic import field_serializer
from sqlmodel import (
    Field,
    Relationship,
    SQLModel,
)
from .company import Company
from .vehicle import (
    Vehicle,
    VehicleResponse,
)

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

    vehicles: list["FleetVehicle"] = Relationship(back_populates="fleet")

class FleetVehicle(SQLModel, table=True):
    __tablename__ = "fleet_vehicle"

    fleet_id: int | None = Field(default=None, foreign_key="fleet.id", primary_key=True)
    vehicle_id: int | None = Field(default=None, foreign_key="vehicle.id", primary_key=True)
    quantity: int

    fleet: Fleet = Relationship(back_populates="vehicles")
    vehicle: Vehicle = Relationship()
