from pydantic import (
    SerializerFunctionWrapHandler as sfWrapHandler,
    field_serializer,
    model_serializer,
)
from sqlmodel import (
    Column,
    Field,
    Relationship,
    SQLModel,
)
from .company import Company
from .lot_config import (
    FleetRunProfile,
    FleetRunProfileJSON,
    VehicleBehaviorConfig,
    VehicleRouteConfig,
)
from .vehicle import (
    Vehicle,
    VehicleResponse,
)

class FleetBase(SQLModel):
    name: str

class FleetVehicleCreate(SQLModel):
    qty: int
    id: str
    route: VehicleRouteConfig | None = None
    behavior: VehicleBehaviorConfig | None = None

    def to_run_profile(self) -> FleetRunProfile | None:
        if self.route is None and self.behavior is None:
            return None
        return FleetRunProfile(route=self.route, behavior=self.behavior)

class FleetCreate(FleetBase):
    vehicles: list[FleetVehicleCreate]

class FleetUpdate(FleetCreate):
    name: str | None = None
    vehicles: list[FleetVehicleCreate] | None = None

class FleetVehicleResponse(VehicleResponse):
    qty: int
    route: VehicleRouteConfig | None = None
    behavior: VehicleBehaviorConfig | None = None

class FleetResponse(FleetCreate):
    id: str | int
    vehicles: list[FleetVehicleResponse]

    @field_serializer('id', when_used='json')
    def serialize_id_to_str(self, id: int):
        return str(id)

class Fleet(FleetBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    company_id: int = Field(foreign_key="company.id")

    vehicles: list["FleetVehicle"] = Relationship(back_populates="fleet", passive_deletes="all")

    @model_serializer(mode='wrap')
    def serialize_model(self, handler: sfWrapHandler) -> dict[str, object]:
        serialized = handler(self)
        vehicles: list[dict[str, object]] = []
        for link in self.vehicles or []:
            v = link.vehicle.model_dump()
            v['qty'] = link.quantity
            if link.run_profile:
                if link.run_profile.route is not None:
                    v['route'] = link.run_profile.route.model_dump(exclude_none=True)
                if link.run_profile.behavior is not None:
                    v['behavior'] = link.run_profile.behavior.model_dump(exclude_none=True)
            vehicles.append(v)
        serialized['vehicles'] = vehicles
        return serialized

class FleetVehicle(SQLModel, table=True):
    __tablename__ = "fleet_vehicle"

    fleet_id: int | None = Field(default=None, foreign_key="fleet.id", primary_key=True)
    vehicle_id: int | None = Field(default=None, foreign_key="vehicle.id", primary_key=True)
    quantity: int
    run_profile: FleetRunProfile | None = Field(default=None, sa_column=Column(FleetRunProfileJSON))

    fleet: Fleet = Relationship(back_populates="vehicles")
    vehicle: Vehicle = Relationship()
