from pydantic import (
    SerializerFunctionWrapHandler as sfWrapHandler,
    model_serializer,
)
from sqlalchemy import Column, JSON
from sqlmodel import (
    Field,
    Relationship,
    SQLModel,
)
from .enum import DeliveryLotState
from libs.time_window_wire import normalize_waypoints_payload
from .delivery import (
    Delivery,
)
from .delivery_lot import DeliveryLot
from .driver import (
    Driver,
)
from .milestone import (
    Milestone,
)
from .vehicle import (
    Vehicle,
)

def _coerce_delivery_id(raw: object) -> int | None:
    if raw is None or isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        return raw
    text = str(raw).strip()
    if text.isdigit():
        return int(text)
    return None

class DeliveryRouteUpdate(SQLModel):
    id: str
    deliveries: list[str]

class DeliveryPlan(SQLModel, table=True):
    __tablename__ = "delivery_plan"

    id: int | None = Field(default=None, primary_key=True)
    delivery_lot_id: int = Field(foreign_key="delivery_lot.id")
    optimizer_id: str
    totals_data: dict | None = Field(default=None, sa_column=Column(JSON))

    lot: DeliveryLot = Relationship(back_populates="plans")
    paths: list["DeliveryPath"] = Relationship(back_populates="plan", passive_deletes="all")

    @model_serializer(mode='wrap')
    def serialize_model(self, handler: sfWrapHandler) -> dict[str, object]:
        serialized = handler(self)
        serialized['state'] = self.lot.state
        if self.optimizer_id:
            serialized['session_id'] = self.optimizer_id
            serialized['optimizer_session_id'] = self.optimizer_id

        delivery_paths: list[dict] = []
        if self.paths:
            routes = []
            for linkp in self.paths:
                r: dict[str, object] = {'id': str(linkp.id)}
                route_data = dict(linkp.route_data or {})
                if route_data.get("optimized_waypoints"):
                    route_data["optimized_waypoints"] = normalize_waypoints_payload(
                        route_data["optimized_waypoints"],
                    )
                if route_data.get("stops"):
                    route_data["stops"] = normalize_waypoints_payload(route_data["stops"])
                arrival_by_delivery: dict[int, object] = {}
                for wp in route_data.get("optimized_waypoints") or []:
                    arrival = wp.get("arrival_time")
                    if arrival is None:
                        continue
                    raw_ids = wp.get("delivery_ids") or [wp.get("delivery_id")]
                    for raw_id in raw_ids:
                        dlv_id = _coerce_delivery_id(raw_id)
                        if dlv_id is not None:
                            arrival_by_delivery[dlv_id] = arrival
                r['milestone'] = linkp.milestone.model_dump()
                r['deliveries'] = []
                for linkd in linkp.deliveries:
                    d = linkd.delivery.model_dump()
                    arrival = arrival_by_delivery.get(int(linkd.delivery_id))
                    if arrival is not None:
                        d['arrival_time'] = arrival
                    r['deliveries'].append(d)
                if linkp.vehicle:
                    r['vehicle'] = linkp.vehicle.model_dump()
                if linkp.driver:
                    r['driver'] = linkp.driver.model_dump()
                if route_data:
                    r.update(route_data)
                    path_payload = dict(route_data)
                    path_payload.setdefault("route_id", route_data.get("route_id") or str(linkp.id))
                    delivery_paths.append(path_payload)
                routes.append(r)
            serialized['routes'] = routes
            if delivery_paths:
                serialized['delivery_paths'] = delivery_paths
        if self.totals_data:
            serialized['totals'] = self.totals_data
        for key in ('id', 'delivery_lot_id', 'optimizer_id', 'totals_data'):
            serialized.pop(key, None)
        return serialized

class DeliveryPath(SQLModel, table=True):
    __tablename__ = "delivery_path"

    id: int | None = Field(default=None, primary_key=True)
    delivery_plan_id: int = Field(foreign_key="delivery_plan.id")
    milestone_id: int = Field(foreign_key="milestone.id")
    vehicle_id: int | None = Field(default=None, foreign_key="vehicle.id")
    driver_id: int | None = Field(default=None, foreign_key="driver.id")
    route_data: dict | None = Field(default=None, sa_column=Column(JSON))

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
