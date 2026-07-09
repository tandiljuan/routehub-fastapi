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


def bulk_link_lot_deliveries(
    db: Session,
    lot_id: int,
    raw_ids: list[str],
    *,
    company_id: int | None = None,
) -> int:
    """Link explicit delivery IDs. Returns rows linked."""
    if not raw_ids:
        return 0
    ids = _int_ids(raw_ids)
    query = select(Delivery.id).where(Delivery.id.in_(ids))
    if company_id is not None:
        query = query.where(Delivery.company_id == company_id)
    existing = set(db.exec(query).all())
    rows = [
        {"delivery_lot_id": lot_id, "delivery_id": dlv_id}
        for dlv_id in ids
        if dlv_id in existing
    ]
    if rows:
        db.exec(insert(DeliveryLotDelivery), params=rows)
    return len(rows)


def bulk_link_lot_drivers(
    db: Session,
    lot_id: int,
    raw_ids: list[str],
    *,
    company_id: int | None = None,
) -> int:
    """Link explicit driver IDs. Returns rows linked."""
    if not raw_ids:
        return 0
    ids = _int_ids(raw_ids)
    query = select(Driver.id).where(Driver.id.in_(ids))
    if company_id is not None:
        query = query.where(Driver.company_id == company_id)
    existing = set(db.exec(query).all())
    rows = [
        {"delivery_lot_id": lot_id, "driver_id": drv_id}
        for drv_id in ids
        if drv_id in existing
    ]
    if rows:
        db.exec(insert(DeliveryLotDriver), params=rows)
    return len(rows)


def replace_lot_deliveries(
    db: Session,
    lot_id: int,
    raw_ids: list[str],
    *,
    company_id: int | None = None,
) -> int:
    """Replace all delivery links for a lot (single DELETE + bulk INSERT, no commit)."""
    db.exec(delete(DeliveryLotDelivery).where(DeliveryLotDelivery.delivery_lot_id == lot_id))
    return bulk_link_lot_deliveries(db, lot_id, raw_ids, company_id=company_id)


def replace_lot_drivers(
    db: Session,
    lot_id: int,
    raw_ids: list[str],
    *,
    company_id: int | None = None,
) -> int:
    """Replace all driver links for a lot (single DELETE + bulk INSERT, no commit)."""
    db.exec(delete(DeliveryLotDriver).where(DeliveryLotDriver.delivery_lot_id == lot_id))
    return bulk_link_lot_drivers(db, lot_id, raw_ids, company_id=company_id)


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


def serialize_plan_poll(state: DeliveryLotState, optimizer_session_id: str | None = None) -> dict:
    out: dict = {"state": state, "routes": None}
    if optimizer_session_id:
        out["session_id"] = optimizer_session_id
        out["optimizer_session_id"] = optimizer_session_id
    return out


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
            .selectinload(DeliveryPathDelivery.delivery)
            .selectinload(Delivery.milestone),
        )
    )
    return db.exec(stmt).first()


def _purge_unlinked_deliveries(db: Session, delivery_ids: list[int]) -> int:
    """Delete deliveries no longer linked to any lot or route path (batched)."""
    if not delivery_ids:
        return 0

    purged = 0
    chunk_size = 5_000
    for offset in range(0, len(delivery_ids), chunk_size):
        chunk = delivery_ids[offset : offset + chunk_size]
        still_in_lot = (
            select(DeliveryLotDelivery.delivery_id)
            .where(DeliveryLotDelivery.delivery_id == Delivery.id)
            .exists()
        )
        still_in_path = (
            select(DeliveryPathDelivery.delivery_id)
            .where(DeliveryPathDelivery.delivery_id == Delivery.id)
            .exists()
        )
        result = db.exec(
            delete(Delivery).where(
                Delivery.id.in_(chunk),
                ~still_in_lot,
                ~still_in_path,
            )
        )
        purged += result.rowcount or 0
    db.flush()
    return purged


def delete_delivery_lot(
    db: Session,
    lot_id: int,
    *,
    purge_deliveries: bool = False,
) -> tuple[bool, int]:
    """Delete lot with plans, paths, and junction rows (ORM cascade is incomplete)."""
    lot = db.get(DeliveryLot, lot_id)
    if not lot:
        return False, 0

    delivery_ids: list[int] = []
    if purge_deliveries:
        delivery_ids = list(
            db.exec(
                select(DeliveryLotDelivery.delivery_id).where(
                    DeliveryLotDelivery.delivery_lot_id == lot_id
                )
            ).all()
        )

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

    purged = _purge_unlinked_deliveries(db, delivery_ids) if purge_deliveries else 0
    return True, purged


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
    """One row per delivery per route.

    When the optimizer merges multiple input addresses at the same coordinate into
    a single waypoint (with all their packages bundled), we must iterate every
    package — not just packages[0] — so every delivery that shared that location
    appears in the route result.
    """
    order_by_delivery: dict[int, int] = {}
    for waypoint in route.optimized_waypoints:
        for pkg in (waypoint.packages or []):
            pkg_id = pkg.package_id
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


def _optimized_waypoints_payload(route, package_to_delivery: dict[str, int]) -> list[dict]:
    """Optimizer visit order with delivery_id + arrival_time for GET /plan consumers."""
    from libs.time_window_wire import normalize_waypoint_payload

    payload: list[dict] = []
    for wp in route.optimized_waypoints or []:
        item = wp.model_dump(mode="json", exclude_none=True)
        # A merged waypoint can bundle packages from several deliveries; expose
        # all of them (delivery_id kept as the first for backward compatibility).
        dlv_ids: list[str] = []
        for pkg in wp.packages or []:
            dlv_id = str(resolve_delivery_id(package_to_delivery, pkg.package_id))
            if dlv_id not in dlv_ids:
                dlv_ids.append(dlv_id)
        if dlv_ids:
            item["delivery_id"] = dlv_ids[0]
            item["delivery_ids"] = dlv_ids
        payload.append(normalize_waypoint_payload(item))
    return payload


def _route_data_from_optimizer(
    route,
    route_index: int,
    *,
    package_to_delivery: dict[str, int] | None = None,
) -> dict:
    data: dict = {
        "route_index": route_index,
        "route_geometry": route.route_geometry,
    }
    if route.route_id is not None:
        data["route_id"] = route.route_id
    if route.distance_km is not None:
        data["total_distance_km"] = route.distance_km
    if route.duration_sec is not None:
        data["total_duration_sec"] = route.duration_sec
    if package_to_delivery is not None:
        waypoints = _optimized_waypoints_payload(route, package_to_delivery)
        if waypoints:
            data["optimized_waypoints"] = waypoints
            data["stops"] = waypoints
            data["num_points"] = len(waypoints)
            arrival_times = [
                wp.get("arrival_time") for wp in waypoints
            ]
            if any(v is not None for v in arrival_times):
                data["arrival_times"] = arrival_times
    for name in (
        "total_packages",
        "load_percentage",
        "route_volume_cm3",
        "executor_capacity_cm3",
        "avg_speed_kmh",
        "stops_per_hour",
        "duration_formatted",
        "duration_hours",
        "duration_minutes",
        "tw_stats",
    ):
        value = getattr(route, name, None)
        if value is not None:
            data[name] = value
    return data


def _totals_data_from_optimizer(totals) -> dict | None:
    if totals is None:
        return None

    data: dict = {}
    for name in (
        "total_routes",
        "total_points",
        "total_distance_km",
        "total_duration_sec",
        "execution_time_sec",
    ):
        value = getattr(totals, name, None)
        if value is not None:
            data[name] = value

    fleet_metrics: dict = {}
    for name in (
        "fleet_size",
        "fleet_capacity_total_cm3",
        "fleet_volume_used_cm3",
        "fleet_efficiency_percentage",
        "fleet_usage_percentage",
    ):
        value = getattr(totals, name, None)
        if value is not None:
            fleet_metrics[name] = value
    if fleet_metrics:
        if totals.total_routes is not None:
            fleet_metrics["routes_count"] = totals.total_routes
        data["fleet_metrics"] = fleet_metrics

    tw_global: dict = {}
    tw_fields = (
        ("tw_total", "total_tw"),
        ("tw_inserted_ok", "inserted_ok"),
        ("tw_violations", "violations"),
        ("tw_fallback_violations", "fallback_violations"),
        ("tw_total_packages", "total_tw_packages"),
        ("tw_violation_percentage", "violation_percentage"),
        ("tw_status", "status"),
    )
    for src, dst in tw_fields:
        value = getattr(totals, src, None)
        if value is not None:
            tw_global[dst] = value
    if tw_global:
        data["time_windows_global"] = tw_global

    for name in (
        "submitted_points",
        "unserved_points",
        "rejection_summary",
        "rejected_deliveries",
    ):
        value = getattr(totals, name, None)
        if value is not None:
            data[name] = value

    submitted = data.get("submitted_points")
    routed = data.get("total_points")
    if submitted is not None and routed is not None and "unserved_points" not in data:
        unserved = int(submitted) - int(routed)
        if unserved > 0:
            data["unserved_points"] = unserved

    return data or None


def _totals_data_from_result(result) -> dict | None:
    """Merge optimizer totals + root-level rejection / submitted fields."""
    totals = getattr(result, "totals", None)
    data = _totals_data_from_optimizer(totals) or {}

    for name in (
        "submitted_points",
        "unserved_points",
        "rejection_summary",
        "rejected_deliveries",
    ):
        if data.get(name) is not None:
            continue
        value = getattr(result, name, None)
        if value is not None:
            data[name] = value

    submitted = data.get("submitted_points")
    routed = data.get("total_points")
    if submitted is not None and routed is not None and data.get("unserved_points") is None:
        unserved = int(submitted) - int(routed)
        if unserved > 0:
            data["unserved_points"] = unserved

    return data or None


def persist_processing_plan_routes(
    db: Session,
    plan_db: DeliveryPlan,
    milestone_id: int,
    routes,
    *,
    result=None,
    totals=None,
    package_to_delivery: dict[str, int],
    wire_type_to_vehicle: dict[str, int],
) -> None:
    """Replace plan paths from a completed optimizer result (called on GET /plan once complete)."""
    clear_plan_paths(db, plan_db.id)

    totals_data = (
        _totals_data_from_result(result)
        if result is not None
        else _totals_data_from_optimizer(totals)
    )
    if totals_data is not None:
        plan_db.totals_data = totals_data
        db.add(plan_db)

    paths: list[DeliveryPath] = []
    for route_index, route in enumerate(routes):
        paths.append(
            DeliveryPath(
                delivery_plan_id=plan_db.id,
                milestone_id=milestone_id,
                vehicle_id=resolve_vehicle_id(wire_type_to_vehicle, route.vehicle_type),
                route_data=_route_data_from_optimizer(
                    route,
                    route_index,
                    package_to_delivery=package_to_delivery,
                ),
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


def apply_draft_plan_routes(
    db: Session,
    plan_db: DeliveryPlan,
    routes,
    *,
    result=None,
    totals=None,
    package_to_delivery: dict[str, int],
) -> None:
    totals_data = (
        _totals_data_from_result(result)
        if result is not None
        else _totals_data_from_optimizer(totals)
    )
    if totals_data is not None:
        plan_db.totals_data = totals_data
        db.add(plan_db)

    for route_index, route in enumerate(routes):
        path_id = int(route.route_id)
        pth_db = db.get(DeliveryPath, path_id)
        if not pth_db or pth_db.delivery_plan_id != plan_db.id:
            continue

        db.exec(
            delete(DeliveryPathDelivery).where(
                DeliveryPathDelivery.delivery_path_id == path_id
            )
        )

        index = (pth_db.route_data or {}).get("route_index", route_index)
        pth_db.route_data = _route_data_from_optimizer(
            route,
            index,
            package_to_delivery=package_to_delivery,
        )
        db.add(pth_db)

        links = delivery_links_for_route(path_id, route, package_to_delivery)
        if links:
            db.add_all(links)
