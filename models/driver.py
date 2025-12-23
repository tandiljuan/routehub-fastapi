from sqlmodel import (
    Column,
    Field,
    JSON,
    SQLModel,
)

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
