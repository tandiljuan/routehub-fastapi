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
from libs.lot_plan_adapter import build_wire_type_to_vehicle_id_map
from libs.package_wire import build_package_id_to_delivery_id_map
from libs.plan_wire import plan_to_wire_payload
from libs.tenant.context import CompanyDep, assert_company_match
from models.bks_optimization import BksOptimization
from models.database import Session as DbSession
from models.delivery_plan import DeliveryPlan
from models.enum import DeliveryLotState
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


def _request(db, lot_db) -> tuple[dict, str]:
    """The lot's plan request (engine wire format) and its hash."""
    plan, _ = build_lot_plan_context(db, lot_db)
    payload = plan_to_wire_payload(plan)
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()
    return payload, digest


def _current_plan(lot_db) -> DeliveryPlan | None:
    """The lot's latest plan, when it has routes to improve."""
    if lot_db.state != DeliveryLotState.PROCESSED or not lot_db.plans:
        return None
    plan_db = lot_db.plans[-1]
    return plan_db if plan_db.paths else None


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
        if not data.get("vehicle_type"):
            raise HTTPException(status_code=422, detail="The current plan does not record its vehicle types; "
                                                        "plan the lot again before optimizing it")
        vtype = str(data["vehicle_type"])
        routes.append({"vehicle_type": names.get(vtype.lower(), vtype), "package_ids": package_ids})
    return routes


def _with_lot(item: dict, row: BksOptimization, stale: bool | None = None) -> dict:
    out = dict(item, lot_id=row.delivery_lot_id, base_plan_id=row.base_plan_id, result_plan_id=row.result_plan_id)
    if stale is not None:
        out["stale"] = stale
    return out


@router.post("/{id}/bks-optimizations", status_code=202, summary="Optimize the lot's plan (BKS)")
def bks_optimizations_post(id: int, body: BksOptimizationCreate, db: DbSession, company_id: CompanyDep):
    client = _client()
    lot_db = _lot(db, id, company_id)
    if lot_db.state in BUSY:
        raise HTTPException(status_code=409, detail="The lot is being planned; wait until it finishes")
    plan_db = _current_plan(lot_db)
    if plan_db is None:
        raise HTTPException(status_code=409, detail="The lot has no plan to improve; plan it first")
    payload, digest = _request(db, lot_db)
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
        db.commit()
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
        raise HTTPException(status_code=409, detail="The lot is being planned; wait until it finishes")
    if _request(db, lot_db)[1] != row.context_hash:
        raise HTTPException(status_code=409, detail={
            "code": "lot_changed",
            "message": "The lot changed after this optimization was requested; its solutions no longer apply"})
    try:
        result = client.routes(company_id, optimization_id, solution_id)
    except BksOptimizerError as exc:
        raise _upstream_error(exc) from exc
    plan_db = DeliveryPlan(delivery_lot_id=lot_db.id, optimizer_id=f"{optimization_id}:{solution_id}", origin="bks")
    db.add(plan_db)
    db.flush()
    try:
        persist_processing_plan_routes(
            db, plan_db, lot_db.milestone.id, result.routes or [], result=result,
            package_to_delivery=build_package_id_to_delivery_id_map(fetch_lot_delivery_rows(db, lot_db.id)),
            wire_type_to_vehicle=build_wire_type_to_vehicle_id_map(lot_db.fleet.vehicles),
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
