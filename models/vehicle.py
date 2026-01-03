from pydantic import field_serializer
from sqlmodel import (
    Column,
    Enum,
    Field,
    SQLModel,
)
from .enum import (
    VehicleCategoryType,
    VehicleConsumptionUnit,
    VehicleEngineType,
    VolumeUnit,
)
from .company import Company

class VehicleBase(SQLModel):
    name: str
    volume: int | None = Field(default=None)
    volume_unit: VolumeUnit | None = Field(default=None, sa_column=Column(Enum(VolumeUnit)))
    consumption: int | None = Field(default=None)
    consumption_unit: VehicleConsumptionUnit | None = Field(default=None, sa_column=Column(Enum(VehicleConsumptionUnit)))
    category_type: VehicleCategoryType | None = Field(default=None, sa_column=Column(Enum(VehicleCategoryType)))
    engine_type: VehicleEngineType | None = Field(default=None, sa_column=Column(Enum(VehicleEngineType)))

class VehicleCreate(VehicleBase):
    pass

class VehicleUpdate(VehicleCreate):
    name: str | None = None

class VehicleResponse(VehicleCreate):
    id: str | int

    @field_serializer('id', when_used='json')
    def serialize_id_to_str(self, id: int):
        return str(id)

class Vehicle(VehicleBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    company_id: int = Field(foreign_key="company.id")
