import math
import os
from typing import Annotated
from fastapi import (
    APIRouter,
    HTTPException,
    Request,
    Response,
)
from fastapi.responses import JSONResponse
from pydantic import Field
from sqlalchemy import func
from sqlmodel import select
from libs.package_wire import (
    build_package_id_to_delivery_id_map,
    build_plan_address,
    parse_lat_lng_from_destination,
)
from libs.lot_persistence import (
    apply_draft_plan_routes,
    bulk_link_lot_deliveries,
    bulk_link_lot_drivers,
    delete_delivery_lot,
    fetch_lot_delivery_rows,
    load_delivery_lot_detail,
    load_delivery_lot_for_plan,
    load_delivery_lots_list,
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
from libs.plan_build import build_plan_context_for_lot, compute_fallback_stops, graph_tag_for_lot
from models.delivery_plan import (
    DeliveryPath,
    DeliveryPlan,
    DeliveryRouteUpdate,
)
from libs.optimizer import Optimizer, OptimizerError
from libs.optimizer.models import (
    DraftPackage,
    DraftRoute,
    DraftRouting,
    DraftSet,
    DraftWaypoint,
)
from libs.tenant.context import CompanyDep, assert_company_match

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


def _raise_optimizer_http_error(exc: OptimizerError) -> None:
    status = 422 if exc.upstream_status == 422 else 502
    detail = str(exc)
    if exc.upstream_body is not None:
        upstream = (
            exc.upstream_body
            if isinstance(exc.upstream_body, str)
            else str(exc.upstream_body)
        )
        if upstream and upstream not in detail:
            detail = f"{detail} | upstream: {upstream[:500]}"
    raise HTTPException(status_code=status, detail=detail) from exc


def _set_optimizer_session_header(response: Response, optimizer_session_id: str | None) -> None:
    if optimizer_session_id:
        response.headers["X-Optimizer-Session-Id"] = optimizer_session_id


def _plan_json(payload: dict, optimizer_session_id: str | None = None) -> JSONResponse:
    """Skip response_model validation — large PROCESSED plans exceed Pydantic limits."""
    headers = {}
    if optimizer_session_id:
        headers["X-Optimizer-Session-Id"] = optimizer_session_id
    return JSONResponse(content=payload, headers=headers)


def _dump_plan_or_500(plan_db: DeliveryPlan, optimizer_session_id: str | None = None) -> JSONResponse:
    try:
        payload = plan_db.model_dump()
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Plan serialization failed: {exc}",
        ) from exc
    return _plan_json(payload, optimizer_session_id or plan_db.optimizer_id)

@router.get(
    "",
    summary="List lots",
    response_model=list[DeliveryLotResponse],
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
)
async def delivery_lots_get(db: DbSession, company_id: CompanyDep):
    # Eager-load relations touched by the serializer; without this nested N+1
    # (per lot: milestone, fleet, links; per delivery: the delivery and its milestone).
    lot_list = load_delivery_lots_list(db, company_id)
    return [l.model_dump() for l in lot_list]

@router.post(
    "",
    summary="Create lot",
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
    company_id: CompanyDep,
):
    lot_dict = post_data.model_dump(exclude={"deliveries", "drivers"})
    lot_dict['company_id'] = company_id
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
    summary="Get lot",
    response_model=DeliveryLotResponse,
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
)
async def delivery_lots_id_get(id: int, db: DbSession, company_id: CompanyDep):
    lot_db = load_delivery_lot_detail(db, id)
    assert_company_match(lot_db, company_id, "Delivery lot")
    return lot_db.model_dump()

@router.patch(
    "/{id}",
    summary="Update lot",
    response_model=DeliveryLotResponse,
    response_model_exclude_unset=True,
    response_model_exclude_none=True,
)
async def delivery_lots_id_patch(
    id: int,
    db: DbSession,
    patch_data: DeliveryLotUpdate,
    company_id: CompanyDep,
):
    lot_db = db.get(DeliveryLot, id)
    assert_company_match(lot_db, company_id, "Delivery lot")

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

@router.delete("/{id}", summary="Delete lot")
async def delivery_lots_id_delete(
    id: int,
    db: DbSession,
    company_id: CompanyDep,
    purge_deliveries: bool = False,
):
    lot_db = db.get(DeliveryLot, id)
    assert_company_match(lot_db, company_id, "Delivery lot")
    deleted, purged_deliveries = delete_delivery_lot(
        db,
        id,
        purge_deliveries=purge_deliveries,
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="Delivery lot not found")
    db.commit()
    return {
        "code": 200,
        "message": "Delivery lot Deleted",
        "purged_deliveries": purged_deliveries,
    }

@router.post(
    "/{id}/plan",
    status_code=202,
    summary="Queue plan",
    description="No body. Sends lot to the optimizer.",
)
async def delivery_lots_id_plan_post(
    id: int,
    db: DbSession,
    company_id: CompanyDep,
):
    if not optimizer:
        raise HTTPException(status_code=500)

    lot_db = load_delivery_lot_for_plan(db, id)
    assert_company_match(lot_db, company_id, "Delivery lot")

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
            graph_tag=graph_tag_for_lot(db, lot_db),
        )
    except LotPlanConfigError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        plan_id = optimizer.send_route_plan(plan=plan)
    except OptimizerError as exc:
        _raise_optimizer_http_error(exc)

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
    summary="Get plan",
    response_model=None,
)
async def delivery_lots_id_plan_get(
    id: int,
    db: DbSession,
    company_id: CompanyDep,
):
    if not optimizer:
        raise HTTPException(status_code=500)

    lot_db = db.get(DeliveryLot, id)
    assert_company_match(lot_db, company_id, "Delivery lot")

    plans = lot_db.plans

    if not plans \
    or DeliveryLotState.UNPROCESSED == lot_db.state:
        raise HTTPException(status_code=404, detail="No routing plan has been created")

    plan_db = plans[-1]

    if DeliveryLotState.PROCESSING == lot_db.state:
        plan_result = optimizer.get_plan_result(task_id=plan_db.optimizer_id)

        if "completed" != plan_result.status:
            return _plan_json(
                serialize_plan_poll(lot_db.state, plan_db.optimizer_id),
                plan_db.optimizer_id,
            )

        package_map = build_package_id_to_delivery_id_map(
            fetch_lot_delivery_rows(db, lot_db.id)
        )
        lot_with_fleet = load_delivery_lot_for_plan(db, lot_db.id)
        wire_vehicle_map = build_wire_type_to_vehicle_id_map(lot_with_fleet.fleet.vehicles)
        try:
            persist_processing_plan_routes(
                db,
                plan_db,
                lot_db.milestone.id,
                plan_result.routes,
                result=plan_result,
                package_to_delivery=package_map,
                wire_type_to_vehicle=wire_vehicle_map,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    elif DeliveryLotState.OPTIMIZING == lot_db.state:
        draft_result = optimizer.get_draft_result(task_id=plan_db.optimizer_id)

        if "failed" == draft_result.status:
            # Re-optimize worker failed — restore the previous PROCESSED plan so the
            # lot doesn't stay stuck in OPTIMIZING (the client re-sends its moves).
            lot_db.state = DeliveryLotState.PROCESSED
            db.add(lot_db)
            db.commit()
            plan_db = load_delivery_plan_detail(db, plan_db.id)
            return _dump_plan_or_500(plan_db)

        if "completed" != draft_result.status:
            return _plan_json(
                serialize_plan_poll(lot_db.state, plan_db.optimizer_id),
                plan_db.optimizer_id,
            )

        package_map = build_package_id_to_delivery_id_map(
            fetch_lot_delivery_rows(db, lot_db.id)
        )
        try:
            apply_draft_plan_routes(
                db,
                plan_db,
                draft_result.routes,
                result=draft_result,
                package_to_delivery=package_map,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    else:
        plan_db = load_delivery_plan_detail(db, plan_db.id)
        return _dump_plan_or_500(plan_db)

    lot_db.state = DeliveryLotState.PROCESSED
    db.add(lot_db)
    db.commit()

    plan_db = load_delivery_plan_detail(db, plan_db.id)
    return _dump_plan_or_500(plan_db)

@router.get(
    "/{id}/plan/status",
    summary="Get optimizer session status",
    response_model=None,
    description=(
        "Poll real-time progress for an async route optimization session. "
        "Use every 2–3 seconds after POST /lots/{id}/plan. "
        "When status=completed and progress_pct=100, fetch the final plan via GET /lots/{id}/plan."
    ),
)
async def delivery_lots_id_plan_status_get(
    id: int,
    db: DbSession,
    company_id: CompanyDep,
):
    if not optimizer:
        raise HTTPException(status_code=500)

    lot_db = db.get(DeliveryLot, id)
    assert_company_match(lot_db, company_id, "Delivery lot")

    if not lot_db.plans or DeliveryLotState.UNPROCESSED == lot_db.state:
        raise HTTPException(status_code=404, detail="No routing plan has been created")

    if DeliveryLotState.PROCESSING != lot_db.state:
        raise HTTPException(
            status_code=409,
            detail="Optimizer status is only available while the plan is processing",
        )

    plan_db = lot_db.plans[-1]
    if not plan_db.optimizer_id:
        raise HTTPException(status_code=404, detail="No optimizer session for this plan")

    status_code, body = optimizer.get_route_status(plan_db.optimizer_id)
    return JSONResponse(
        content=body,
        status_code=status_code,
        headers={"X-Optimizer-Session-Id": plan_db.optimizer_id},
    )

@router.patch(
    "/{id}/plan",
    summary="Re-optimize routes",
    status_code=202,
)
async def delivery_lots_id_plan_patch(
    id: int,
    db: DbSession,
    patch_data: Annotated[list[DeliveryRouteUpdate], Field(min_length=1)],
    company_id: CompanyDep,
):
    if not optimizer:
        raise HTTPException(status_code=500)

    lot_db = db.get(DeliveryLot, id)
    assert_company_match(lot_db, company_id, "Delivery lot")

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
        tag=graph_tag_for_lot(db, lot_db),
        optimization_params=DraftRouting(),
        routes=routes,
    )

    try:
        draft_id = optimizer.send_route_draft(draft=draft)
    except OptimizerError as exc:
        _raise_optimizer_http_error(exc)

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
