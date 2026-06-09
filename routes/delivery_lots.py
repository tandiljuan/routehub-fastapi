import math
import os
import re
from datetime import datetime
from typing import Annotated
from fastapi import (
    APIRouter,
    HTTPException,
    Request,
    Response,
)
from pydantic import Field
from sqlalchemy import delete, func
from sqlmodel import select
from libs.package_wire import (
    build_package_id_to_delivery_id_map,
    build_plan_address,
    parse_lat_lng_from_destination,
    resolve_delivery_id,
)
from libs.lot_persistence import (
    bulk_link_lot_deliveries,
    bulk_link_lot_drivers,
    delete_delivery_lot,
    delivery_links_for_route,
    fetch_lot_delivery_rows,
    load_delivery_lot_detail,
    load_delivery_lot_for_plan,
    load_delivery_plan_detail,
    persist_processing_plan_routes,
    replace_lot_deliveries,
    replace_lot_drivers,
    serialize_lot_created,
    serialize_plan_poll,
)
from models.database import Session as DbSession
from models.enum import DeliveryLotState
from models.delivery_lot import (
    DeliveryLot,
    DeliveryLotCreate,
    DeliveryLotDelivery,
    DeliveryLotResponse,
    DeliveryLotUpdate,
)
from models.lot_config import LotConfig, merge_config_data
from libs.lot_plan_adapter import (
    LotPlanConfigError,
    build_wire_type_to_vehicle_id_map,
)
from models.delivery_plan import (
    DeliveryPath,
    DeliveryPathDelivery,
    DeliveryPlan,
    DeliveryPlanResponse,
    DeliveryRouteUpdate,
)
from models.driver import Driver
from libs.optimizer import Optimizer
from libs.optimizer.models import (
    DraftPackage,
    DraftRoute,
    DraftRouting,
    DraftSet,
    DraftWaypoint,
    PlanAddress,
    PlanClustering,
    PlanContext,
    PlanPackage,
    PlanRebalance,
    PlanRouting,
    PlanSettings,
    PlanSettingsPreprocessing,
    PlanVehicle,
    PlanVehicleDistance,
    PlanVehicleQuantity,
)

OPTIMIZER_HOST = os.environ.get("OPTIMIZER_HOST")
OPTIMIZER_PORT = os.environ.get("OPTIMIZER_PORT")
OPTIMIZER_AUTH = os.environ.get("OPTIMIZER_AUTH")

optimizer = None

if OPTIMIZER_HOST and OPTIMIZER_PORT:
    optimizer = Optimizer(
        OPTIMIZER_HOST,
        OPTIMIZER_PORT,
        OPTIMIZER_AUTH,
    )

router = APIRouter(
    prefix="/lots",
    tags=["lots"],
)

@router.get(
    "",
    response_model=list[DeliveryLotResponse],
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
)
async def delivery_lots_get(db: DbSession):
    response = []
    lot_list = db.exec(select(DeliveryLot)).all()
    for l in lot_list:
        response.append(l.model_dump())
    return response

@router.post(
    "",
    response_model=DeliveryLotResponse,
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
    status_code=201,
)
async def delivery_lots_post(
    request: Request,
    response: Response,
    db: DbSession,
    post_data: DeliveryLotCreate,
):
    lot_dict = post_data.model_dump(exclude={"deliveries", "drivers"})
    lot_dict['company_id'] = 1
    lot_dict = DeliveryLot.normalize_submitted_dict(lot_dict)
    lot_db = DeliveryLot.model_validate(lot_dict)

    db.add(lot_db)
    db.flush()

    linked_count = bulk_link_lot_deliveries(db, lot_db.id, post_data.deliveries)
    bulk_link_lot_drivers(db, lot_db.id, post_data.drivers or [])
    db.commit()

    lot_url = request.url_for("delivery_lots_id_get", id=lot_db.id)
    response.headers["location"] = f"{lot_url}"

    return serialize_lot_created(db, lot_db.id, delivery_count=linked_count)

@router.get(
    "/{id}",
    name="delivery_lots_id_get",
    response_model=DeliveryLotResponse,
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
)
async def delivery_lots_id_get(id: int, db: DbSession):
    lot_db = db.get(DeliveryLot, id)
    if not lot_db:
        raise HTTPException(status_code=404, detail="Delivery lot not found")
    return lot_db.model_dump()

@router.patch(
    "/{id}",
    response_model=DeliveryLotResponse,
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
)
async def delivery_lots_id_patch(
    id: int,
    db: DbSession,
    patch_data: DeliveryLotUpdate,
):
    lot_db = db.get(DeliveryLot, id)
    if not lot_db:
        raise HTTPException(status_code=404, detail="Delivery lot not found")

    patch_dict = patch_data.model_dump(
        exclude_unset=True,
        exclude={"deliveries", "drivers"},
    )
    if patch_dict:
        patch_dict = DeliveryLot.normalize_submitted_dict(patch_dict)
        if "config_data" in patch_dict:
            patch_dict["config_data"] = merge_config_data(
                lot_db.config_data,
                patch_dict["config_data"],
            )
        lot_db.sqlmodel_update(patch_dict)
        db.add(lot_db)

    if patch_data.deliveries is not None:
        replace_lot_deliveries(db, lot_db.id, patch_data.deliveries)

    if patch_data.drivers is not None:
        replace_lot_drivers(db, lot_db.id, patch_data.drivers)

    db.commit()

    lot_db = load_delivery_lot_detail(db, id)
    return lot_db.model_dump()

@router.delete("/{id}")
async def delivery_lots_id_delete(
    id: int,
    db: DbSession,
):
    if not delete_delivery_lot(db, id):
        raise HTTPException(status_code=404, detail="Delivery lot not found")
    db.commit()
    return {"code": 200, "message": "Delivery lot Deleted"}

@router.post(
    "/{id}/plan",
    status_code=202,
)
async def delivery_lots_id_plan_post(
    id: int,
    db: DbSession,
):
    if not optimizer:
        raise HTTPException(status_code=500)

    lot_db = db.get(DeliveryLot, id)
    if not lot_db:
        raise HTTPException(status_code=404, detail="Delivery lot not found")

    if DeliveryLotState.PROCESSING == lot_db.state:
        raise HTTPException(status_code=409, detail="The plan is being processed")

    if DeliveryLotState.OPTIMIZING == lot_db.state:
        raise HTTPException(status_code=409, detail="The plan is being optimized")

    # Count amount of vehicles
    v_sum = 0
    for link in lot_db.fleet.vehicles:
        v_sum += link.quantity

    if not v_sum:
        raise HTTPException(status_code=422, detail=f"No vehicles have been loaded into the lot")

    # Count amount of addresses
    a_sum = db.exec(
        select(func.count()).where(DeliveryLotDelivery.delivery_lot_id == lot_db.id)
    ).one()

    if not a_sum:
        raise HTTPException(status_code=422, detail=f"No deliveries have been loaded into the lot")

    limit_stop_min = math.ceil(a_sum * 0.95)
    limit_stop_max = math.floor(a_sum * 1.05)

    route_stops_min = math.floor(limit_stop_min / v_sum)
    route_stops_min = lot_db.route_stops_min if lot_db.route_stops_min else route_stops_min
    route_stops_max = math.ceil(limit_stop_max / v_sum)
    route_stops_max = lot_db.route_stops_max if lot_db.route_stops_max else route_stops_max

    # Total amount of min and max stops
    t_stop_min = v_sum * route_stops_min
    t_stop_max = v_sum * route_stops_max

    if t_stop_min > limit_stop_min or t_stop_max < limit_stop_max:
        raise HTTPException(status_code=422, detail=f"Minimum stops ({t_stop_min}) must be at least 5% below the addresses ({a_sum}) and maximum stops ({t_stop_max}) must be at least %5 above them")

    priority = 0
    vehicles = []
    for link in lot_db.fleet.vehicles:
        priority += 1
        pv = PlanVehicle(
            type=str(link.vehicle.id),
            quantity=link.quantity,
            priority_vehicle=priority,
            overflow_vehicle=(True if 1 == priority else False),
        )

        smin = route_stops_min
        smax = route_stops_max
        if smin or smax:
            vq = PlanVehicleQuantity(
                min=smin,
                max=smax,
            )
            pv.deliveries_qty = vq

        lmin = lot_db.route_length_min
        lmax = lot_db.route_length_max
        if smin or smax:
            vl = PlanVehicleDistance(
                min_km=lmin,
                max_km=lmax,
            )
            pv.distance_limits = vl

        vehicles.append(pv)

    geo_rgx = re.compile(r'([+-]?[\d\.]+)')

    addresses = []
    for link in lot_db.deliveries:
        dlv = link.delivery

        p = PlanPackage(
            package_id=str(dlv.id),
        )
        packages = [p]

        geo = geo_rgx.findall(dlv.destination)

        addresses.append(PlanAddress(
            lat=float(geo[0]),
            lng=float(geo[1]),
            packages=packages,
        ))

    max_size_cluster = math.ceil(a_sum / v_sum)
    min_size_cluster = math.floor(max_size_cluster / 2)
    clustering = PlanClustering(
        min_size_cluster=min_size_cluster,
        max_size_cluster=max_size_cluster,
    )

    routing = PlanRouting()
    rebalance = PlanRebalance()

    preprocessing = PlanSettingsPreprocessing(
        preprocessing_batch_size = max_size_cluster * 3,
    )

    settings = PlanSettings(
        preprocessing = preprocessing,
    )

    geo = geo_rgx.findall(lot_db.milestone.location)

    plan = PlanContext(
        date=datetime.today().strftime('%Y-%m-%d'),
        origin_lat=float(geo[0]),
        origin_lng=float(geo[1]),
        tag=lot_db.milestone.name.strip().replace(' ', '_').upper(),
        vehicles=vehicles,
        addresses=addresses,
        clustering=clustering,
        routing=routing,
        rebalance=rebalance,
        settings=settings,
    )

    plan_id = optimizer.send_route_plan(plan=plan)

    plan_db = DeliveryPlan.model_validate({
        "delivery_lot_id": lot_db.id,
        "optimizer_id": plan_id,
    })
    db.add(plan_db)
    lot_db.state = DeliveryLotState.PROCESSING
    db.add(lot_db)
    db.commit()

    return {
        "code": 202,
        "message": "Delivery plan queued for processing",
    }

@router.get(
    "/{id}/plan",
    response_model=DeliveryPlanResponse,
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
)
async def delivery_lots_id_plan_get(
    id: int,
    db: DbSession,
):
    if not optimizer:
        raise HTTPException(status_code=500)

    lot_db = db.get(DeliveryLot, id)
    if not lot_db:
        raise HTTPException(status_code=404, detail="Delivery lot not found")

    plans = lot_db.plans

    if not plans \
    or DeliveryLotState.UNPROCESSED == lot_db.state:
        raise HTTPException(status_code=404, detail="No routing plan has been created")

    plan_db = plans[-1]

    if DeliveryLotState.PROCESSING == lot_db.state:
        plan_result = optimizer.get_plan_result(task_id=plan_db.optimizer_id)

        if "completed" != plan_result.status:
            return serialize_plan_poll(lot_db.state)

        package_map = build_package_id_to_delivery_id_map(
            fetch_lot_delivery_rows(db, lot_db.id)
        )
        lot_with_fleet = load_delivery_lot_for_plan(db, lot_db.id)
        wire_vehicle_map = build_wire_type_to_vehicle_id_map(lot_with_fleet.fleet.vehicles)
        persist_processing_plan_routes(
            db,
            plan_db,
            lot_db.milestone.id,
            plan_result.routes,
            package_to_delivery=package_map,
            wire_type_to_vehicle=wire_vehicle_map,
        )

    elif DeliveryLotState.OPTIMIZING == lot_db.state:
        draft_result = optimizer.get_draft_result(task_id=plan_db.optimizer_id)

        if "completed" != draft_result.status:
            return serialize_plan_poll(lot_db.state)

        query = select(DeliveryPath, DeliveryPathDelivery)
        query = query.join(DeliveryPathDelivery)

        package_map = build_package_id_to_delivery_id_map(
            fetch_lot_delivery_rows(db, lot_db.id)
        )
        for route in draft_result.routes:
            for waypoint in route.optimized_waypoints:
                dlv_id = resolve_delivery_id(
                    package_map, waypoint.packages[0].package_id,
                )
                dlv_qry = query.where(
                    DeliveryPath.delivery_plan_id == plan_db.id,
                    DeliveryPathDelivery.delivery_id == dlv_id,
                )
                link = db.exec(dlv_qry).first()
                if link is not None:
                    db.delete(link[-1])

            pth_db = db.get(DeliveryPath, route.route_id)
            db.exec(
                delete(DeliveryPathDelivery).where(
                    DeliveryPathDelivery.delivery_path_id == pth_db.id
                )
            )

            links = delivery_links_for_route(
                pth_db.id,
                route,
                package_map,
            )
            db.add_all(links)
            db.commit()

    else:
        # Return (custom serialized) Plan
        return plan_db.model_dump()

    # Update Lot
    lot_db.state=DeliveryLotState.PROCESSED
    db.add(lot_db)
    db.commit()

    # Return (custom serialized) Plan
    db.refresh(plan_db)
    return plan_db.model_dump()

@router.patch(
    "/{id}/plan",
    status_code=202,
)
async def delivery_lots_id_plan_patch(
    id: int,
    db: DbSession,
    patch_data: Annotated[list[DeliveryRouteUpdate], Field(min_length=1)],
):
    if not optimizer:
        raise HTTPException(status_code=500)

    lot_db = db.get(DeliveryLot, id)
    if not lot_db:
        raise HTTPException(status_code=404, detail="Delivery lot not found")

    if DeliveryLotState.PROCESSED != lot_db.state:
        raise HTTPException(status_code=409, detail="The plan must be 'PROCESSED' to be updated")

    geo_rgx = re.compile(r'([+-]?[\d\.]+)')

    routes = []

    # Iterate list of routes
    for route in patch_data:

        # Get route (path) from DB
        pth_db = db.get(DeliveryPath, route.id)
        if not pth_db or pth_db.plan.lot.id != id:
            raise HTTPException(status_code=404, detail=f"Route not found (id: '{route.id}')")

        waypoints = []

        # Iterate list of points
        for dlv_id in route.deliveries:

            # Get point (relation) from DB
            dld_db = db.get(DeliveryLotDelivery, (id, dlv_id))
            if not dld_db:
                raise HTTPException(status_code=404, detail=f"Delivery not found (id: '{dlv_id}')")
            dlv_db = dld_db.delivery

            # Build waypoint object
            p = DraftPackage(
                package_id=str(dlv_db.id),
            )
            packages = [p]
            geo = geo_rgx.findall(dlv_db.destination)
            waypoints.append(DraftWaypoint(
                lat=float(geo[0]),
                lng=float(geo[1]),
                packages=packages,
            ))

        # Append non empty list of waypoints
        if len(waypoints):
            routes.append(DraftRoute(
                route_id=str(pth_db.id),
                waypoints=waypoints,
            ))

        # Remove empty routes (paths)
        else:
            db.delete(pth_db)
            db.commit()

    if not len(routes):
        return {
            "code": 202,
            "message": "Routes processed",
        }

    geo = geo_rgx.findall(lot_db.milestone.location)

    draft = DraftSet(
        origin_lat=float(geo[0]),
        origin_lng=float(geo[1]),
        tag=lot_db.milestone.name.strip().replace(' ', '_').upper(),
        optimization_params=DraftRouting(),
        routes=routes,
    )

    draft_id = optimizer.send_route_draft(draft=draft)

    # Change Lot State
    lot_db.state=DeliveryLotState.OPTIMIZING
    db.add(lot_db)
    db.commit()

    plan_db = lot_db.plans[-1]
    plan_db.optimizer_id = draft_id

    # Update Plan
    db.add(plan_db)
    db.commit()

    return {
        "code": 202,
        "message": "Routes queued for optimization",
    }
