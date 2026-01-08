from pydantic import (
    SerializerFunctionWrapHandler as sfWrapHandler,
    model_serializer,
)
from sqlmodel import (
    Field,
    Relationship,
    SQLModel,
)
from .enum import DeliveryLotState
from .delivery import (
    Delivery,
    DeliveryResponse,
)
from .delivery_lot import DeliveryLot
from .driver import (
    Driver,
    DriverResponse,
)
from .milestone import (
    Milestone,
    MilestoneResponse,
)
from .vehicle import (
    Vehicle,
    VehicleResponse,
)

class RouteResponse(SQLModel):
    milestone: MilestoneResponse
    deliveries: list[DeliveryResponse]
    vehicle: VehicleResponse | None = None
    driver: DriverResponse | None = None

class DeliveryPlanResponse(SQLModel):
    state: DeliveryLotState
    routes: list[RouteResponse] | None = None

class DeliveryPlan(SQLModel, table=True):
    __tablename__ = "delivery_plan"

    id: int | None = Field(default=None, primary_key=True)
    delivery_lot_id: int = Field(foreign_key="delivery_lot.id")
    optimizer_id: str

    lot: DeliveryLot = Relationship()
    paths: list["DeliveryPath"] = Relationship(back_populates="plan", passive_deletes="all")

    @model_serializer(mode='wrap')
    def serialize_model(self, handler: sfWrapHandler) -> dict[str, object]:
        # Output from default serializer
        serialized = handler(self)
        # Build 'state' attribute
        serialized['state'] = self.lot.state
        # Build 'routes' attribute from relations
        if len(self.paths):
            routes = []
            for linkp in self.paths:
                r = {}
                # Build 'route.state' attribute
                r['milestone'] = linkp.milestone.model_dump()
                # Build 'route.deliveries' attribute
                r['deliveries'] = []
                for linkd in linkp.deliveries:
                    d = linkd.delivery.model_dump()
                    r['deliveries'].append(d)
                # Build 'route.vehicle' attribute
                if linkp.vehicle:
                    v = linkp.vehicle.model_dump()
                    r['vehicle'] = v
                # Build 'route.driver' attribute
                if linkp.driver:
                    d = linkp.driver.model_dump()
                    r['vehicle'] = d
                routes.append(r)
            serialized['routes'] = routes
        # Return (custom) serialized model
        return serialized

class DeliveryPath(SQLModel, table=True):
    __tablename__ = "delivery_path"

    id: int | None = Field(default=None, primary_key=True)
    delivery_plan_id: int = Field(foreign_key="delivery_plan.id")
    milestone_id: int = Field(foreign_key="milestone.id")
    vehicle_id: int | None = Field(default=None, foreign_key="vehicle.id")
    driver_id: int | None = Field(default=None, foreign_key="driver.id")

    plan: DeliveryPlan = Relationship()
    milestone: Milestone = Relationship()
    vehicle: Vehicle = Relationship()
    driver: Driver = Relationship()
    deliveries: list["DeliveryPathDelivery"] = Relationship(back_populates="path", passive_deletes="all")

class DeliveryPathDelivery(SQLModel, table=True):
    __tablename__ = "delivery_path_delivery"

    delivery_path_id: int | None = Field(default=None, foreign_key="delivery_path.id", primary_key=True)
    delivery_id: int | None = Field(default=None, foreign_key="delivery.id", primary_key=True)
    delivery_order: int

    path: DeliveryPath = Relationship(back_populates="deliveries")
    delivery: Delivery = Relationship()
