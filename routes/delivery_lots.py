import math
import os
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
from models.lot_config import LotConfig, merge_lot_config
from libs.lot_plan_adapter import (
    LotPlanConfigError,
    build_wire_type_to_vehicle_id_map,
)
from libs.plan_build import build_plan_context_for_lot, compute_fallback_stops
from models.delivery_plan import (
    DeliveryPath,
    DeliveryPathDelivery,
    DeliveryPlan,
    DeliveryPlanResponse,
    DeliveryRouteUpdate,
)
from libs.optimizer import Optimizer
from libs.optimizer.models import (
    DraftPackage,
    DraftRoute,
    DraftRouting,
    DraftSet,
    DraftWaypoint,
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
    lot_db = load_delivery_lot_detail(db, id)
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
            patch_dict["config_data"] = merge_lot_config(
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

    lot_db = load_delivery_lot_for_plan(db, id)
    if not lot_db:
        raise HTTPException(status_code=404, detail="Delivery lot not found")

    if DeliveryLotState.PROCESSING == lot_db.state:
        raise HTTPException(status_code=409, detail="The plan is being processed")

    if DeliveryLotState.OPTIMIZING == lot_db.state:
        raise HTTPException(status_code=409, detail="The plan is being optimized")

    v_sum = 0
    for link in lot_db.fleet.vehicles:
        v_sum += link.quantity

    if not v_sum:
        raise HTTPException(status_code=422, detail=f"No vehicles have been loaded into the lot")

    a_sum = db.exec(
        select(func.count()).where(DeliveryLotDelivery.delivery_lot_id == lot_db.id)
    ).one()

    if not a_sum:
        raise HTTPException(status_code=422, detail=f"No deliveries have been loaded into the lot")

    limit_stop_min = math.ceil(a_sum * 0.95)
    limit_stop_max = math.floor(a_sum * 1.05)

    route_stops_min, route_stops_max = compute_fallback_stops(a_sum, v_sum, lot_db)

    t_stop_min = v_sum * route_stops_min
    t_stop_max = v_sum * route_stops_max

    if t_stop_min > limit_stop_min or t_stop_max < limit_stop_max:
        raise HTTPException(status_code=422, detail=f"Minimum stops ({t_stop_min}) must be at least 5% below the addresses ({a_sum}) and maximum stops ({t_stop_max}) must be at least %5 above them")

    lot_config = lot_db.config_data or LotConfig()

    delivery_rows = fetch_lot_delivery_rows(db, lot_db.id)

    try:
        plan = build_plan_context_for_lot(
            lot_db=lot_db,
            lot_config=lot_config,
            fleet_links=lot_db.fleet.vehicles,
            delivery_rows=delivery_rows,
            fallback_stops_min=route_stops_min,
            fallback_stops_max=route_stops_max,
        )
    except LotPlanConfigError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

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

    else:
        plan_db = load_delivery_plan_detail(db, plan_db.id)
        return plan_db.model_dump()

    lot_db.state = DeliveryLotState.PROCESSED
    db.add(lot_db)
    db.commit()

    plan_db = load_delivery_plan_detail(db, plan_db.id)
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

            addr = build_plan_address(
                dlv_db.destination,
                dlv_db.extra,
                delivery_id=int(dlv_db.id),
            )
            waypoints.append(DraftWaypoint(
                lat=addr.lat,
                lng=addr.lng,
                packages=[
                    DraftPackage(package_id=p.package_id) for p in addr.packages
                ],
            ))

        # Append non empty list of waypoints
        if len(waypoints):
            routes.append(DraftRoute(
                route_id=str(pth_db.id),
                waypoints=waypoints,
            ))

        else:
            db.delete(pth_db)

    if not len(routes):
        db.commit()
        return {
            "code": 202,
            "message": "Routes processed",
        }

    origin_lat, origin_lng = parse_lat_lng_from_destination(lot_db.milestone.location)

    draft = DraftSet(
        origin_lat=origin_lat,
        origin_lng=origin_lng,
        tag=lot_db.milestone.name.strip().replace(' ', '_').upper(),
        optimization_params=DraftRouting(),
        routes=routes,
    )

    draft_id = optimizer.send_route_draft(draft=draft)

    lot_db.state = DeliveryLotState.OPTIMIZING
    db.add(lot_db)
    plan_db = lot_db.plans[-1]
    plan_db.optimizer_id = draft_id
    db.add(plan_db)
    db.commit()

    return {
        "code": 202,
        "message": "Routes queued for optimization",
    }
