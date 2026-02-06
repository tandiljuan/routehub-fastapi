import math
import os
import re
from datetime import datetime
from fastapi import (
    APIRouter,
    HTTPException,
    Request,
    Response,
)
from sqlmodel import select
from models.database import Session as DbSession
from models.enum import DeliveryLotState
from models.delivery import Delivery
from models.delivery_lot import (
    DeliveryLot,
    DeliveryLotCreate,
    DeliveryLotDelivery,
    DeliveryLotDriver,
    DeliveryLotResponse,
    DeliveryLotUpdate,
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
    # Add Company ID to submitted data
    lot_dict = post_data.model_dump()
    lot_dict['company_id'] = 1
    lot_dict = DeliveryLot.normalize_submitted_dict(lot_dict)
    lot_db = DeliveryLot.model_validate(lot_dict)

    # Create Lot
    db.add(lot_db)
    db.commit()

    # Create relations between Lot and Deliveries
    post_deliveries = post_data.deliveries or []
    for dlv_id in post_deliveries:
        dlv_id = int(dlv_id)
        dlv_db = db.get(Delivery, dlv_id)
        if dlv_db:
            link = DeliveryLotDelivery(
                lot=lot_db,
                delivery=dlv_db,
            )
            lot_db.deliveries.append(link)
            db.add(lot_db)
            db.commit()

    # Create relations between Lot and Drivers
    post_drivers = post_data.drivers or []
    for drv_id in post_drivers:
        drv_id = int(drv_id)
        drv_db = db.get(Driver, drv_id)
        if drv_db:
            link = DeliveryLotDriver(
                lot=lot_db,
                driver=drv_db,
            )
            lot_db.drivers.append(link)
            db.add(lot_db)
            db.commit()

    # Set location header
    lot_url = request.url_for("delivery_lots_id_get", id=lot_db.id)
    response.headers["location"] = f"{lot_url}"

    # Return (custom serialized) Lot
    db.refresh(lot_db)
    return lot_db.model_dump()

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

    # Update Lot
    lot_dict = patch_data.model_dump(exclude_unset=True)
    lot_dict = DeliveryLot.normalize_submitted_dict(lot_dict)
    lot_db.sqlmodel_update(lot_dict)
    db.add(lot_db)
    db.commit()

    # Update relations between Lot and Deliveries
    post_deliveries = patch_data.deliveries or []
    if len(post_deliveries):
        # Remove existing relation
        for link in lot_db.deliveries:
            db.delete(link)
            db.commit()
        # Load submitted data
        for dlv_id in post_deliveries:
            dlv_id = int(dlv_id)
            dlv_db = db.get(Delivery, dlv_id)
            if dlv_db:
                link = DeliveryLotDelivery(
                    lot=lot_db,
                    delivery=dlv_db,
                )
                lot_db.deliveries.append(link)
                db.add(lot_db)
                db.commit()

    # Update relations between Lot and Drivers
    post_drivers = patch_data.drivers or []
    if len(post_drivers):
        # Remove existing relation
        for link in lot_db.drivers:
            db.delete(link)
            db.commit()
        for drv_id in post_deliveries:
            drv_id = int(drv_id)
            drv_db = db.get(Driver, drv_id)
            if drv_db:
                link = DeliveryLotDriver(
                    lot=lot_db,
                    driver=drv_db,
                )
                lot_db.drivers.append(link)
                db.add(lot_db)
                db.commit()

    # Return (custom serialized) Lot
    db.refresh(lot_db)
    return lot_db.model_dump()

@router.delete("/{id}")
async def delivery_lots_id_delete(
    id: int,
    db: DbSession,
):
    lot_db = db.get(DeliveryLot, id)
    if not lot_db:
        raise HTTPException(status_code=404, detail="Delivery lot not found")
    db.delete(lot_db)
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

    if DeliveryLotState.PROCESSED == lot_db.state:
        raise HTTPException(status_code=409, detail="The plan is being processed")

    if DeliveryLotState.OPTIMIZING == lot_db.state:
        raise HTTPException(status_code=409, detail="The plan is being optimized")

    v_sum = 0
    priority = 0
    vehicles = []
    for link in lot_db.fleet.vehicles:
        priority += 1
        v_sum += link.quantity
        pv = PlanVehicle(
            type=str(link.vehicle.id),
            quantity=link.quantity,
            priority_vehicle=priority,
            overflow_vehicle=(True if 1 == priority else False),
        )

        smin = lot_db.route_stops_min
        smax = lot_db.route_stops_max
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

    a_sum = 0
    addresses = []
    for link in lot_db.deliveries:
        a_sum += 1
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

    # Create Plan
    db.add(plan_db)
    db.commit()

    # Update Lot
    lot_db.state=DeliveryLotState.PROCESSING
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
            # Return (custom serialized) Plan
            return plan_db.model_dump()

        # Create paths (routes)
        for r in plan_result.routes:
            pth_db = DeliveryPath(
                delivery_plan_id=plan_db.id,
                milestone_id=lot_db.milestone.id,
                vehicle_id=r.vehicle_type,
            )
            db.add(pth_db)
            db.commit()
            # Create relations between Path and Deliveries
            for w in r.optimized_waypoints:
                link = DeliveryPathDelivery(
                    delivery_path_id=pth_db.id,
                    delivery_id=w.packages[0].package_id,
                    delivery_order=w.order,
                )
                pth_db.deliveries.append(link)
                db.add(pth_db)
                db.commit()

    elif DeliveryLotState.OPTIMIZING == lot_db.state:
        draft_result = optimizer.get_draft_result(task_id=plan_db.optimizer_id)

        if "completed" != draft_result.status:
            # Return (custom serialized) Plan
            return plan_db.model_dump()

        query = select(DeliveryPath, DeliveryPathDelivery)
        query = query.join(DeliveryPathDelivery)

        for route in draft_result.routes:
            # Loop new points and remove old relations
            for waypoint in route.optimized_waypoints:
                dlv_id = waypoint.packages[0].package_id
                dlv_qry = query.where(
                    DeliveryPath.delivery_plan_id == plan_db.id,
                    DeliveryPathDelivery.delivery_id == dlv_id,
                )
                link = db.exec(dlv_qry).first()
                if None != link:
                    db.delete(link[-1])
                    db.commit()

            pth_db = db.get(DeliveryPath, route.route_id)

            # Loop old points and remove old relations
            for link in pth_db.deliveries:
                db.delete(link)
                db.commit()

            # Loop new points and create new relations
            for waypoint in route.optimized_waypoints:
                dlv_id = waypoint.packages[0].package_id
                dlv_order = waypoint.order
                link = DeliveryPathDelivery(
                    delivery_path_id=pth_db.id,
                    delivery_id=dlv_id,
                    delivery_order=dlv_order,
                )
                pth_db.deliveries.append(link)
                db.add(pth_db)
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
    patch_data: list[DeliveryRouteUpdate],
):
    if not optimizer:
        raise HTTPException(status_code=500)

    lot_db = db.get(DeliveryLot, id)
    if not lot_db:
        raise HTTPException(status_code=404, detail="Delivery lot not found")

    if DeliveryLotState.PROCESSED != lot_db.state:
        raise HTTPException(status_code=409, detail="The plan must be 'PROCESSED' to be updated")

    # Change Lot State
    lot_db.state=DeliveryLotState.OPTIMIZING
    db.add(lot_db)
    db.commit()

    geo_rgx = re.compile(r'([+-]?[\d\.]+)')

    routes = []
    for route in patch_data:
        waypoints = []
        for dlv_id in route.deliveries:
            dlv_db = db.get(Delivery, dlv_id)
            if not dlv_db:
                raise HTTPException(status_code=404, detail=f"Delivery not found (id: '{dlv_id}')")
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
        routes.append(DraftRoute(
            route_id=str(route.id),
            waypoints=waypoints,
        ))

    geo = geo_rgx.findall(lot_db.milestone.location)

    draft = DraftSet(
        origin_lat=float(geo[0]),
        origin_lng=float(geo[1]),
        tag=lot_db.milestone.name.strip().replace(' ', '_').upper(),
        optimization_params=DraftRouting(),
        routes=routes,
    )

    draft_id = optimizer.send_route_draft(draft=draft)

    plan_db = lot_db.plans[-1]
    plan_db.optimizer_id = draft_id

    # Update Plan
    db.add(plan_db)
    db.commit()

    return {
        "code": 202,
        "message": "Routes queued for optimization",
    }
