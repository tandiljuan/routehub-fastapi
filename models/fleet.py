from sqlmodel import SQLModel

class FleetBase(SQLModel):
    name: str

class FleetVehicleCreate(SQLModel):
    qty: int
    id: str

class FleetCreate(FleetBase):
    vehicles: list[FleetVehicleCreate]
