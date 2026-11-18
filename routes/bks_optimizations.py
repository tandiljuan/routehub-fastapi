"""BKS optimizations of a lot: improve the lot's current plan with vepathos-bks-optimizer.

The lot's plan request (the same one the engine receives) goes to the service with the lot's current plan as the
starting solution. The service searches in the background and keeps the solution cards; RouteHub stores only the
authorization record (BksOptimization) and reads state, cards and routes from the service.

Picking a solution creates a new plan for the lot (origin "bks") with the solution's routes, stored the same way
as an engine result; it becomes the lot's latest plan. The lot stays editable while an optimization runs: if the
plan request built today differs from the one sent, the optimization is stale and its solutions cannot be picked.

With BKS_OPTIMIZER_ENABLED=false (default) every route answers 404.
"""
from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from sqlmodel import select

import libs.bks_optimizer as bks
from libs.bks_optimizer import BksOptimizerError
from libs.lot_persistence import (
    fetch_lot_delivery_rows,
    load_delivery_lot_for_plan,
    load_delivery_plan_detail,
    persist_processing_plan_routes,
)
from libs.lot_plan_adapter import _FleetLinkStub, _stub_vehicle, build_wire_type_to_vehicle_id_map
from libs.package_wire import build_package_id_to_delivery_id_map
from libs.plan_wire import wire_request
from libs.tenant.context import CompanyDep, assert_company_match
from models.bks_optimization import BksOptimization
from models.database import Session as DbSession
from models.delivery_plan import DeliveryPlan
from models.enum import DeliveryLotState
from models.lot_config import LotConfig
from models.vehicle import Vehicle
from routes.delivery_lots import _dump_plan_or_500, build_lot_plan_context

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/lots", tags=["bks-optimizations"])

BUSY = (DeliveryLotState.PROCESSING, DeliveryLotState.OPTIMIZING)


class BksOptimizationCreate(BaseModel):
    """What the caller may choose; everything else comes from the lot."""

    options: dict[str, Any] | None = Field(
        default=None,
        description="vepathos-bks-optimizer options (recipe, objective, fleet, effort, stop, solutions); "
                    "the service validates them",
    )
    label: str | None = Field(default=None, max_length=120)


def _client():
    client = bks.client()
    if client is None:
        raise HTTPException(status_code=404, detail="BKS optimization is disabled. Set BKS_OPTIMIZER_ENABLED=true.")
    return client


def _upstream_error(exc: BksOptimizerError) -> HTTPException:
    """The service's error with the same meaning: its 4xx as-is, anything else as 502."""
    status = exc.status if exc.status and 400 <= exc.status < 500 else 502
    headers = {"Retry-After": exc.retry_after} if exc.retry_after else None
    return HTTPException(status_code=status, headers=headers,
                         detail={"code": exc.code or "bks_optimizer_unavailable", "message": str(exc),
                                 "details": exc.details})


def _lot(db, lot_id: int, company_id: int):
    lot_db = load_delivery_lot_for_plan(db, lot_id)
    assert_company_match(lot_db, company_id, "Delivery lot")
    return lot_db


def _record(db, lot_db, optimization_id: str) -> BksOptimization:
    row = db.get(BksOptimization, optimization_id)
    if row is None or row.delivery_lot_id != lot_db.id or row.company_id != lot_db.company_id:
        raise HTTPException(status_code=404, detail="BKS optimization not found")
    return row


def _request(db, lot_db, keep: bool = False) -> tuple[dict, str]:
    """The plan request of the lot's latest plan (engine wire format, as it was sent) and its hash.

    A plan from before requests were stored gets one built from the lot now: with the lot's fleet, or, when the
    run-only fleet is gone, with the vehicles its routes used. ``keep`` stores that rebuilt request on the plan, so
    the optimization and its later checks compare against the same request."""
    latest = lot_db.plans[-1] if lot_db.plans else None
    if latest is not None and latest.request_data:
        payload = latest.request_data
    else:
        links = None if lot_db.fleet is not None else _fleet_from_routes(lot_db, latest)
        plan, _ = build_lot_plan_context(db, lot_db, links)
        payload = wire_request(plan)
        if keep and latest is not None:
            latest.request_data = payload
            db.add(latest)
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()
    return payload, digest


def _fleet_from_routes(lot_db, plan_db: DeliveryPlan | None) -> list[_FleetLinkStub]:
    """A stand-in fleet for a lot whose run-only fleet was deleted: one vehicle per route of its latest plan, typed
    as the plan named it. A type the lot's configuration overrides keeps that spelling, so its rules apply."""
    if plan_db is None or not plan_db.paths:
        raise HTTPException(status_code=409, detail={
            "code": "lot_request_unavailable",
            "message": "The lot has no fleet and no routes to rebuild it from: plan it again first"})
    config = lot_db.config_data or LotConfig()
    overrides = {o.vehicle_id.lower(): o.vehicle_id
                 for o in (config.vehicles.overrides if config.vehicles and config.vehicles.overrides else [])}
    fleet: dict[str, _FleetLinkStub] = {}
    for path in plan_db.paths:
        typed = str((path.route_data or {}).get("vehicle_type") or "")
        vehicle = path.vehicle
        if not typed and vehicle is None:
            raise HTTPException(status_code=409, detail={
                "code": "lot_request_unavailable",
                "message": "A route of the lot's plan has no vehicle: plan the lot again first"})
        name = getattr(vehicle, "name", None) if vehicle is not None else None
        wire = overrides.get(typed.lower()) or (name if name and name.lower() == typed.lower() else None) \
            or name or typed
        link = fleet.get(wire.lower())
        if link is None:
            fleet[wire.lower()] = _FleetLinkStub(
                1, vehicle if vehicle is not None else _stub_vehicle(wire), wire_type=wire,
                catalog_vehicle_id=str(vehicle.id) if vehicle is not None else None)
        else:
            link.quantity += 1
    return list(fleet.values())


def _current_plan(lot_db) -> DeliveryPlan | None:
    """The lot's latest plan, when it has routes to improve."""
    if lot_db.state != DeliveryLotState.PROCESSED or not lot_db.plans:
        return None
    plan_db = lot_db.plans[-1]
    return plan_db if plan_db.paths else None


def _vehicle_ids(db, lot_db) -> dict[str, int]:
    """Wire vehicle type → catalog vehicle id. From the lot's fleet; when the run-only fleet is gone, from the
    vehicles the latest plan's routes used (the type as the engine echoed it) and the company's catalog (the
    request names vehicles by catalog name or id)."""
    if lot_db.fleet is not None:
        return build_wire_type_to_vehicle_id_map(lot_db.fleet.vehicles)
    mapping: dict[str, int] = {}
    for path in (lot_db.plans[-1].paths if lot_db.plans else []):
        typed = (path.route_data or {}).get("vehicle_type")
        if typed and path.vehicle_id is not None:
            mapping.setdefault(str(typed), int(path.vehicle_id))
            mapping.setdefault(str(typed).lower(), int(path.vehicle_id))
    for vehicle in db.exec(select(Vehicle).where(Vehicle.company_id == lot_db.company_id)).all():
        mapping.setdefault(str(vehicle.id), int(vehicle.id))
        if vehicle.name:
            mapping.setdefault(vehicle.name, int(vehicle.id))
            mapping.setdefault(vehicle.name.lower(), int(vehicle.id))
    return mapping


def baseline_routes(plan_db: DeliveryPlan, vehicle_types: list[str]) -> list[dict]:
    """The plan's routes as the service's starting solution: vehicle type and package ids in visit order. The type
    is written as the plan request names it (``vehicle_types``): the engine may echo it in another case."""
    names = {str(t).lower(): str(t) for t in vehicle_types}
    routes = []
    for path in sorted(plan_db.paths, key=lambda p: (p.route_data or {}).get("route_index", 0)):
        data = path.route_data or {}
        package_ids = [str(pkg["package_id"]) for wp in data.get("optimized_waypoints") or []
                       for pkg in wp.get("packages") or [] if pkg.get("package_id") is not None]
        if not package_ids:
            continue
        # A route re-sequenced in place ("start at this stop") keeps its vehicle but not the type the engine echoed.
        typed = data.get("vehicle_type") or (getattr(path.vehicle, "name", None) if path.vehicle is not None else None)
        if not typed:
            raise HTTPException(status_code=422, detail={
                "code": "plan_without_vehicle_types",
                "message": "The current plan does not record its vehicle types; plan the lot again before optimizing it"})
        vtype = str(typed)
        route = {"vehicle_type": names.get(vtype.lower(), vtype), "package_ids": package_ids}
        # The rule the optimizer routed it by, so the service measures the plan with the same one. Plans stored
        # before the optimizer reported it carry none: the service then goes by the plan request.
        if data.get("weight_routes") in ("length", "travel_time"):
            route["weight_routes"] = data["weight_routes"]
        routes.append(route)
    return routes


def _with_lot(item: dict, row: BksOptimization, stale: bool | None = None) -> dict:
    out = dict(item, lot_id=row.delivery_lot_id, base_plan_id=row.base_plan_id, result_plan_id=row.result_plan_id)
    if stale is not None:
        out["stale"] = stale
    return out


def _service_request(db, lot_db, body: BksOptimizationCreate, keep: bool = False):
    """The service's request for the lot (its plan request, the current plan as baseline, the caller's options),
    the lot's current plan and the request's hash. Raises 409/422 when the lot cannot be optimized now."""
    if lot_db.state in BUSY:
        raise HTTPException(status_code=409, detail={"code": "lot_busy",
                                                     "message": "The lot is being planned; wait until it finishes"})
    plan_db = _current_plan(lot_db)
    if plan_db is None:
        raise HTTPException(status_code=409, detail={"code": "lot_not_planned",
                                                     "message": "The lot has no plan to improve; plan it first"})
    payload, digest = _request(db, lot_db, keep=keep)
    options = dict(body.options or {}, **({"label": body.label} if body.label else {}))
    ref = {"lot_id": str(lot_db.id), "plan_id": str(plan_db.id)}
    if lot_db.milestone is not None and lot_db.milestone.name:  # the service files the run under the lot's depot
        ref["depot"] = lot_db.milestone.name
    if payload.get("date"):
        ref["day"] = str(payload["date"])[:10]
    request = {"external_ref": ref, "request": payload,
               "baseline": {"source": "plan", "routes": baseline_routes(
                   plan_db, [v.get("type") for v in payload.get("vehicles") or [] if v.get("type")])},
               "options": options}
    return request, plan_db, digest


def _blocking(detail) -> dict:
    """An HTTPException detail as the service's error body."""
    if isinstance(detail, dict) and detail.get("code"):
        return {"code": detail["code"], "message": detail.get("message") or "", "details": detail.get("details")}
    return {"code": "lot_not_optimizable", "message": str(detail), "details": None}


@router.post("/{id}/bks-optimizations/preflight", summary="Check whether the lot's plan can be optimized (BKS)")
def bks_optimizations_preflight(id: int, body: BksOptimizationCreate, db: DbSession, company_id: CompanyDep):
    """The same checks as starting one, without starting it. Always 200 for a lot of the caller: ``ok`` false with
    ``blocking`` (code, message) when the lot or the service would refuse it."""
    client = _client()
    lot_db = _lot(db, id, company_id)
    try:
        request, _, _ = _service_request(db, lot_db, body)
        return client.preflight(company_id, request)
    except HTTPException as exc:
        if exc.status_code >= 500:
            raise
        return {"ok": False, "blocking": [_blocking(exc.detail)]}
    except BksOptimizerError as exc:
        if not exc.status or not 400 <= exc.status < 500 or exc.status == 429:
            raise _upstream_error(exc) from exc
        return {"ok": False, "blocking": [{"code": exc.code or "bks_optimizer_refused", "message": str(exc),
                                           "details": exc.details}]}


@router.post("/{id}/bks-optimizations", status_code=202, summary="Optimize the lot's plan (BKS)")
def bks_optimizations_post(id: int, body: BksOptimizationCreate, db: DbSession, company_id: CompanyDep):
    client = _client()
    lot_db = _lot(db, id, company_id)
    request, plan_db, digest = _service_request(db, lot_db, body, keep=True)
    options = request["options"]
    key = "lot-{}-plan-{}-{}".format(lot_db.id, plan_db.id, hashlib.sha256(
        (digest + json.dumps(options, sort_keys=True)).encode()).hexdigest()[:24])
    try:
        accepted = client.submit(company_id, request, key)
    except BksOptimizerError as exc:
        raise _upstream_error(exc) from exc
    row = db.get(BksOptimization, accepted["optimization_id"])
    if row is None:
        row = BksOptimization(optimization_id=accepted["optimization_id"], company_id=lot_db.company_id,
                              delivery_lot_id=lot_db.id, base_plan_id=plan_db.id, context_hash=digest,
                              label=body.label)
        db.add(row)
    db.commit()  # the record, and the plan's rebuilt request
    logger.info("lot.bks.queue company=%s lot=%s plan=%s optimization=%s", company_id, id, plan_db.id,
                row.optimization_id)
    return _with_lot(accepted, row)


@router.get("/{id}/bks-optimizations", summary="List the lot's BKS optimizations")
def bks_optimizations_list(id: int, db: DbSession, company_id: CompanyDep):
    client = _client()
    lot_db = _lot(db, id, company_id)
    rows = {r.optimization_id: r for r in db.exec(
        select(BksOptimization).where(BksOptimization.delivery_lot_id == lot_db.id)).all()}
    try:
        items = client.list(company_id, lot_id=str(lot_db.id))
    except BksOptimizerError as exc:
        raise _upstream_error(exc) from exc
    return {"items": [_with_lot(i, rows[i["optimization_id"]]) for i in items if i["optimization_id"] in rows]}


@router.get("/{id}/bks-optimizations/{optimization_id}", summary="Get a BKS optimization of the lot")
def bks_optimizations_get(id: int, optimization_id: str, db: DbSession, company_id: CompanyDep):
    client = _client()
    lot_db = _lot(db, id, company_id)
    row = _record(db, lot_db, optimization_id)
    try:
        item = client.get(company_id, optimization_id)
    except BksOptimizerError as exc:
        raise _upstream_error(exc) from exc
    return _with_lot(item, row, stale=_request(db, lot_db)[1] != row.context_hash)


@router.post("/{id}/bks-optimizations/{optimization_id}/cancel", summary="Cancel a BKS optimization")
def bks_optimizations_cancel(id: int, optimization_id: str, db: DbSession, company_id: CompanyDep):
    client = _client()
    row = _record(db, _lot(db, id, company_id), optimization_id)
    try:
        return _with_lot(client.cancel(company_id, optimization_id), row)
    except BksOptimizerError as exc:
        raise _upstream_error(exc) from exc


@router.get("/{id}/bks-optimizations/{optimization_id}/solutions", summary="The optimization's solution cards")
def bks_optimizations_solutions(id: int, optimization_id: str, request: Request, db: DbSession,
                                company_id: CompanyDep):
    """Query parameters (valid, kind, sort, order, max, keep, …) are passed to the service as-is."""
    client = _client()
    _record(db, _lot(db, id, company_id), optimization_id)
    try:
        return client.solutions(company_id, optimization_id, dict(request.query_params))
    except BksOptimizerError as exc:
        raise _upstream_error(exc) from exc


@router.get("/{id}/bks-optimizations/{optimization_id}/solutions/{solution_id}", summary="One solution card")
def bks_optimizations_solution(id: int, optimization_id: str, solution_id: str, db: DbSession,
                               company_id: CompanyDep):
    client = _client()
    _record(db, _lot(db, id, company_id), optimization_id)
    try:
        return client.solution(company_id, optimization_id, solution_id)
    except BksOptimizerError as exc:
        raise _upstream_error(exc) from exc


@router.post("/{id}/bks-optimizations/{optimization_id}/solutions/{solution_id}/select",
             summary="Apply a solution to the lot", response_model=None)
def bks_optimizations_select(id: int, optimization_id: str, solution_id: str, db: DbSession,
                             company_id: CompanyDep):
    """Creates a new plan for the lot (origin "bks") with the solution's routes and returns it like GET /plan."""
    client = _client()
    lot_db = _lot(db, id, company_id)
    row = _record(db, lot_db, optimization_id)
    if lot_db.state in BUSY:
        raise HTTPException(status_code=409, detail={"code": "lot_busy",
                                                     "message": "The lot is being planned; wait until it finishes"})
    if _request(db, lot_db)[1] != row.context_hash:
        raise HTTPException(status_code=409, detail={
            "code": "lot_changed",
            "message": "The lot changed after this optimization was requested; its solutions no longer apply"})
    try:
        result = client.routes(company_id, optimization_id, solution_id)
    except BksOptimizerError as exc:
        raise _upstream_error(exc) from exc
    base_request = lot_db.plans[-1].request_data if lot_db.plans else None
    # The applied solution answers the same request: it keeps it, so the lot can be optimized again from it.
    plan_db = DeliveryPlan(delivery_lot_id=lot_db.id, optimizer_id=f"{optimization_id}:{solution_id}", origin="bks",
                           request_data=base_request)
    db.add(plan_db)
    db.flush()
    try:
        persist_processing_plan_routes(
            db, plan_db, lot_db.milestone.id, result.routes or [], result=result,
            package_to_delivery=build_package_id_to_delivery_id_map(fetch_lot_delivery_rows(db, lot_db.id)),
            wire_type_to_vehicle=_vehicle_ids(db, lot_db),
        )
        client.select(company_id, optimization_id, solution_id)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except BksOptimizerError as exc:
        db.rollback()
        raise _upstream_error(exc) from exc
    lot_db.state = DeliveryLotState.PROCESSED
    row.selected_solution_id, row.result_plan_id = solution_id, plan_db.id
    db.add(lot_db)
    db.add(row)
    db.commit()
    logger.info("lot.bks.select company=%s lot=%s optimization=%s solution=%s plan=%s", company_id, id,
                optimization_id, solution_id, plan_db.id)
    return _dump_plan_or_500(load_delivery_plan_detail(db, plan_db.id))
