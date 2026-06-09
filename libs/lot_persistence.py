from __future__ import annotations

from sqlalchemy import delete, func, insert
from sqlalchemy.orm import selectinload
from sqlmodel import Session, select

from libs.lot_plan_adapter import resolve_vehicle_id
from libs.package_wire import resolve_delivery_id
from models.enum import DeliveryLotState
from models.delivery import Delivery
from models.delivery_lot import DeliveryLot, DeliveryLotDelivery, DeliveryLotDriver
from models.delivery_plan import DeliveryPath, DeliveryPathDelivery, DeliveryPlan
from models.driver import Driver
from models.fleet import Fleet, FleetVehicle


def _int_ids(raw_ids: list[str]) -> list[int]:
    return [int(i) for i in raw_ids]


def bulk_link_lot_deliveries(db: Session, lot_id: int, raw_ids: list[str]) -> int:
    """Link explicit delivery IDs. Returns rows linked."""
    if not raw_ids:
        return 0
    ids = _int_ids(raw_ids)
    existing = set(db.exec(select(Delivery.id).where(Delivery.id.in_(ids))).all())
    rows = [
        {"delivery_lot_id": lot_id, "delivery_id": dlv_id}
        for dlv_id in ids
        if dlv_id in existing
    ]
    if rows:
        db.exec(insert(DeliveryLotDelivery), params=rows)
    return len(rows)


def bulk_link_lot_drivers(db: Session, lot_id: int, raw_ids: list[str]) -> int:
    """Link explicit driver IDs. Returns rows linked."""
    if not raw_ids:
        return 0
    ids = _int_ids(raw_ids)
    existing = set(db.exec(select(Driver.id).where(Driver.id.in_(ids))).all())
    rows = [
        {"delivery_lot_id": lot_id, "driver_id": drv_id}
        for drv_id in ids
        if drv_id in existing
    ]
    if rows:
        db.exec(insert(DeliveryLotDriver), params=rows)
    return len(rows)


def replace_lot_deliveries(db: Session, lot_id: int, raw_ids: list[str]) -> int:
    """Replace all delivery links for a lot (single DELETE + bulk INSERT, no commit)."""
    db.exec(delete(DeliveryLotDelivery).where(DeliveryLotDelivery.delivery_lot_id == lot_id))
    return bulk_link_lot_deliveries(db, lot_id, raw_ids)


def replace_lot_drivers(db: Session, lot_id: int, raw_ids: list[str]) -> int:
    """Replace all driver links for a lot (single DELETE + bulk INSERT, no commit)."""
    db.exec(delete(DeliveryLotDriver).where(DeliveryLotDriver.delivery_lot_id == lot_id))
    return bulk_link_lot_drivers(db, lot_id, raw_ids)


def count_lot_deliveries(db: Session, lot_id: int) -> int:
    """Count linked deliveries for a lot without loading ORM relations."""
    return db.exec(
        select(func.count())
        .select_from(DeliveryLotDelivery)
        .where(DeliveryLotDelivery.delivery_lot_id == lot_id)
    ).one()


def load_delivery_lot_for_plan(db: Session, lot_id: int) -> DeliveryLot | None:
    """Lot + milestone + fleet for POST /plan, without loading delivery relations."""
    stmt = (
        select(DeliveryLot)
        .where(DeliveryLot.id == lot_id)
        .options(
            selectinload(DeliveryLot.milestone),
            selectinload(DeliveryLot.fleet).selectinload(Fleet.vehicles).selectinload(FleetVehicle.vehicle),
        )
    )
    return db.exec(stmt).first()


def fetch_lot_delivery_rows(db: Session, lot_id: int) -> list[tuple[int, str, dict | None]]:
    """(delivery_id, destination, extra) for each delivery in the lot."""
    stmt = (
        select(Delivery.id, Delivery.destination, Delivery.extra)
        .join(DeliveryLotDelivery, DeliveryLotDelivery.delivery_id == Delivery.id)
        .where(DeliveryLotDelivery.delivery_lot_id == lot_id)
        .order_by(Delivery.id)
    )
    return db.exec(stmt).all()


def _lot_limits_payload(lot: DeliveryLot) -> tuple[dict | None, dict | None]:
    """Extract legacy vehicle_limits and route_limits dicts from flat lot columns."""
    vehicle_limits = {}
    if lot.vehicle_volume_min:
        vehicle_limits["volume_min"] = lot.vehicle_volume_min
    if lot.vehicle_volume_max:
        vehicle_limits["volume_max"] = lot.vehicle_volume_max
    if lot.vehicle_capacity_min:
        vehicle_limits["capacity_min"] = lot.vehicle_capacity_min
    if lot.vehicle_capacity_max:
        vehicle_limits["capacity_max"] = lot.vehicle_capacity_max

    route_limits = {}
    if lot.route_stops_min:
        route_limits["stops_min"] = lot.route_stops_min
    if lot.route_stops_max:
        route_limits["stops_max"] = lot.route_stops_max
    if lot.route_length_min:
        route_limits["length_min"] = lot.route_length_min
    if lot.route_length_max:
        route_limits["length_max"] = lot.route_length_max
    if lot.route_length_unit:
        route_limits["length_unit"] = lot.route_length_unit
    if lot.route_time_min:
        route_limits["time_min"] = lot.route_time_min
    if lot.route_time_max:
        route_limits["time_max"] = lot.route_time_max
    if lot.route_time_unit:
        route_limits["time_unit"] = lot.route_time_unit

    return (
        vehicle_limits or None,
        route_limits or None,
    )


def serialize_lot_created(db: Session, lot_id: int, delivery_count: int | None = None) -> dict:
    """Lot response after POST without loading delivery_lot_delivery rows (use GET for full list)."""
    lot = db.exec(
        select(DeliveryLot)
        .where(DeliveryLot.id == lot_id)
        .options(
            selectinload(DeliveryLot.milestone),
            selectinload(DeliveryLot.fleet).selectinload(Fleet.vehicles).selectinload(FleetVehicle.vehicle),
            selectinload(DeliveryLot.drivers).selectinload(DeliveryLotDriver.driver),
        )
    ).first()
    if not lot:
        return {}

    vehicle_limits, route_limits = _lot_limits_payload(lot)
    drivers = []
    if lot.drivers:
        drivers = [link.driver.model_dump() for link in lot.drivers]

    return {
        "id": str(lot.id),
        "state": lot.state,
        "milestone": lot.milestone.model_dump() if lot.milestone else None,
        "fleet": lot.fleet.model_dump() if lot.fleet else None,
        "drivers": drivers,
        "deliveries": [],
        "delivery_count": (
            delivery_count if delivery_count is not None else count_lot_deliveries(db, lot_id)
        ),
        "vehicle_limits": vehicle_limits,
        "route_limits": route_limits,
        "config": (
            lot.config_data.model_dump(mode="json") if lot.config_data else None
        ),
    }


def serialize_plan_poll(state: DeliveryLotState) -> dict:
    return {"state": state, "routes": None}


def load_delivery_lot_detail(db: Session, lot_id: int) -> DeliveryLot | None:
    """Lot + all relations (deliveries, drivers, fleet) for GET /lots/{id}."""
    stmt = (
        select(DeliveryLot)
        .where(DeliveryLot.id == lot_id)
        .options(
            selectinload(DeliveryLot.milestone),
            selectinload(DeliveryLot.fleet).selectinload(Fleet.vehicles).selectinload(FleetVehicle.vehicle),
            selectinload(DeliveryLot.deliveries).selectinload(DeliveryLotDelivery.delivery),
            selectinload(DeliveryLot.drivers).selectinload(DeliveryLotDriver.driver),
        )
    )
    return db.exec(stmt).first()


def load_delivery_plan_detail(db: Session, plan_id: int) -> DeliveryPlan | None:
    """Plan + paths + per-path deliveries for GET /lots/{id}/plan."""
    stmt = (
        select(DeliveryPlan)
        .where(DeliveryPlan.id == plan_id)
        .options(
            selectinload(DeliveryPlan.lot),
            selectinload(DeliveryPlan.paths).selectinload(DeliveryPath.milestone),
            selectinload(DeliveryPlan.paths).selectinload(DeliveryPath.vehicle),
            selectinload(DeliveryPlan.paths).selectinload(DeliveryPath.driver),
            selectinload(DeliveryPlan.paths)
            .selectinload(DeliveryPath.deliveries)
            .selectinload(DeliveryPathDelivery.delivery),
        )
    )
    return db.exec(stmt).first()


def delete_delivery_lot(db: Session, lot_id: int) -> bool:
    """Delete lot with plans, paths, and junction rows (ORM cascade is incomplete)."""
    lot = db.get(DeliveryLot, lot_id)
    if not lot:
        return False

    plan_ids = db.exec(
        select(DeliveryPlan.id).where(DeliveryPlan.delivery_lot_id == lot_id)
    ).all()
    for plan_id in plan_ids:
        clear_plan_paths(db, plan_id)
    if plan_ids:
        db.exec(delete(DeliveryPlan).where(DeliveryPlan.delivery_lot_id == lot_id))

    db.exec(delete(DeliveryLotDelivery).where(DeliveryLotDelivery.delivery_lot_id == lot_id))
    db.exec(delete(DeliveryLotDriver).where(DeliveryLotDriver.delivery_lot_id == lot_id))
    db.delete(lot)
    db.flush()
    return True


def clear_plan_paths(db: Session, plan_id: int) -> None:
    """Remove paths/links for a plan (idempotent retry before re-persist)."""
    path_ids = db.exec(
        select(DeliveryPath.id).where(DeliveryPath.delivery_plan_id == plan_id)
    ).all()
    if not path_ids:
        return
    db.exec(
        delete(DeliveryPathDelivery).where(DeliveryPathDelivery.delivery_path_id.in_(path_ids))
    )
    db.exec(delete(DeliveryPath).where(DeliveryPath.delivery_plan_id == plan_id))
    db.flush()


def delivery_links_for_route(
    path_id: int,
    route,
    package_to_delivery: dict[str, int],
) -> list[DeliveryPathDelivery]:
    """One row per delivery per route; multiple packages at same address share delivery_id."""
    order_by_delivery: dict[int, int] = {}
    for waypoint in route.optimized_waypoints:
        pkg_id = waypoint.packages[0].package_id
        dlv_id = resolve_delivery_id(package_to_delivery, pkg_id)
        order = waypoint.order
        prev = order_by_delivery.get(dlv_id)
        if prev is None or order < prev:
            order_by_delivery[dlv_id] = order
    return [
        DeliveryPathDelivery(
            delivery_path_id=path_id,
            delivery_id=dlv_id,
            delivery_order=order,
        )
        for dlv_id, order in sorted(order_by_delivery.items(), key=lambda item: item[1])
    ]


def persist_processing_plan_routes(
    db: Session,
    plan_db: DeliveryPlan,
    milestone_id: int,
    routes,
    *,
    package_to_delivery: dict[str, int],
    wire_type_to_vehicle: dict[str, int],
) -> None:
    """Replace plan paths from a completed optimizer result (called on GET /plan once complete)."""
    clear_plan_paths(db, plan_db.id)

    paths: list[DeliveryPath] = []
    for route in routes:
        paths.append(
            DeliveryPath(
                delivery_plan_id=plan_db.id,
                milestone_id=milestone_id,
                vehicle_id=resolve_vehicle_id(wire_type_to_vehicle, route.vehicle_type),
            )
        )
    db.add_all(paths)
    db.flush()

    links: list[DeliveryPathDelivery] = []
    for path, route in zip(paths, routes):
        links.extend(
            delivery_links_for_route(path.id, route, package_to_delivery)
        )
    if links:
        db.add_all(links)
