from pydantic import field_serializer
from sqlmodel import (
    Column,
    Field,
    JSON,
    SQLModel,
)
from .company import Company
from .vehicle import VehicleResponse

class DriverBase(SQLModel):
    first_name: str
    last_name: str | None = Field(default=None)
    work_schedules: list[str] | None = Field(default=None, sa_column=Column(JSON))
    start_point: str | None = Field(default=None)
    end_point: str | None = Field(default=None)
    work_areas: list[list[str]] | None = Field(default=None, sa_column=Column(JSON))

class DriverVehicleCreate(SQLModel):
    qty: int
    id: str

class DriverCreate(DriverBase):
    vehicles: list[DriverVehicleCreate] | None = None

class DriverVehicleResponse(VehicleResponse):
    qty: int

class DriverResponse(DriverCreate):
    id: str | int
    vehicles: list[DriverVehicleResponse] | None = None

    @field_serializer('id', when_used='json')
    def serialize_id_to_str(self, id: int):
        return str(id)

class Driver(DriverBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    company_id: int = Field(foreign_key="company.id")
