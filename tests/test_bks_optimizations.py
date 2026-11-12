"""BKS optimizations of a lot (routes/bks_optimizations.py) against a fake vepathos-bks-optimizer.

Checks the request sent (the lot's plan request, the current plan as the starting solution, the lot reference and
an idempotency key), that RouteHub only reaches optimizations through a lot of the caller's workspace, the stale
rule (a lot that changed cannot take a solution) and that picking a solution creates a new "bks" plan with the
solution's routes, stored like an engine result.
"""
import json
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("RDBMS_URL", "sqlite://")

import httpx
from fastapi import HTTPException
from sqlmodel import select

import models.bks_optimization  # noqa: F401 — registers the table
import routes.bks_optimizations as bks_route
from libs.bks_optimizer import BksOptimizer, BksOptimizerError
from libs.optimizer.models import ResultSet
from models.bks_optimization import BksOptimization
from models.delivery import Delivery
from models.delivery_lot import DeliveryLot
from models.delivery_plan import DeliveryPath, DeliveryPlan
from models.enum import DeliveryLotState
from tests.test_plan_failure import _LotPlanCase

WAYPOINT = lambda order, *pkgs: {"order": order, "lat": -34.6, "lng": -58.4,
                                 "packages": [{"package_id": p} for p in pkgs]}
RESULT = ResultSet.model_validate({"status": "completed", "routes": [
    {"route_id": "r1", "vehicle_type": "van", "route_geometry": [[-34.6, -58.4]],
     "optimized_waypoints": [WAYPOINT(0), WAYPOINT(1, "12"), WAYPOINT(2, "11")], "total_distance_km": 9.5}],
    "totals": {"total_routes": 1, "total_points": 2}})


class FakeBks:
    """The service: records calls, answers like vepathos-bks-optimizer."""

    def __init__(self, fail=None):
        self.calls, self.fail = [], fail

    def _call(self, name, *args):
        self.calls.append((name, *args))
        if self.fail and self.fail[0] == name:
            raise self.fail[1]

    def submit(self, company_id, body, key):
        self._call("submit", company_id, body, key)
        return {"optimization_id": "bko_000000000001", "status": "queued", "poll_after_seconds": 5}

    def get(self, company_id, oid):
        self._call("get", company_id, oid)
        return {"optimization_id": oid, "status": "completed", "recommended_solution_id": "sol_3"}

    def list(self, company_id, lot_id=None):
        self._call("list", company_id, lot_id)
        return [{"optimization_id": "bko_000000000001", "status": "running"},
                {"optimization_id": "bko_otro_lote", "status": "running"}]

    def cancel(self, company_id, oid):
        self._call("cancel", company_id, oid)
        return {"optimization_id": oid, "status": "running"}

    def solutions(self, company_id, oid, params=None):
        self._call("solutions", company_id, oid, params)
        return {"items": [], "total": 0}

    def solution(self, company_id, oid, sid):
        self._call("solution", company_id, oid, sid)
        return {"solution_id": sid}

    def routes(self, company_id, oid, sid):
        self._call("routes", company_id, oid, sid)
        return RESULT

    def select(self, company_id, oid, sid):
        self._call("select", company_id, oid, sid)
        return {"solution_id": sid}


class _BksCase(_LotPlanCase):
    def setUp(self):
        super().setUp()
        self.fake = FakeBks()
        self.digest = "hash-1"
        patches = [patch.object(bks_route.bks, "client", lambda: self.fake),
                   patch.object(bks_route, "_request",
                                lambda db, lot: ({"addresses": [], "vehicles": [{"type": "van"}]}, self.digest)),
                   patch.object(bks_route, "build_wire_type_to_vehicle_id_map", lambda links: {"van": 1})]  # the fleet
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def _processed_lot(self, company_id=1):
        for dlv_id in (11, 12, 13):
            if self.db.get(Delivery, dlv_id) is None:
                self.db.add(Delivery(id=dlv_id, destination="-34.6,-58.4", company_id=1, milestone_id=self.milestone.id))
        lot_id = self._seed(DeliveryLotState.PROCESSED)
        lot = self.db.get(DeliveryLot, lot_id)
        lot.company_id = company_id
        plan = self.db.exec(select(DeliveryPlan).where(DeliveryPlan.delivery_lot_id == lot_id)).first()
        self.db.add(DeliveryPath(delivery_plan_id=plan.id, milestone_id=self.milestone.id, route_data={
            "route_index": 0, "vehicle_type": "VAN",  # the engine echoes the type in another case
            "optimized_waypoints": [WAYPOINT(0), WAYPOINT(1, "11"), WAYPOINT(2, "12", "13")]}))
        self.db.add(lot)
        self.db.commit()
        return lot_id, plan.id

    def _post(self, lot_id, **body):
        return bks_route.bks_optimizations_post(id=lot_id, body=bks_route.BksOptimizationCreate(**body), db=self.db,
                                                company_id=1)


class TestRequest(_BksCase):
    def test_sends_the_lot_request_with_the_current_plan_as_baseline(self):
        lot_id, plan_id = self._processed_lot()
        out = self._post(lot_id, options={"recipe": "rapida"}, label="Lote 1")
        (_, company, body, key), = [c for c in self.fake.calls if c[0] == "submit"]
        self.assertEqual(company, 1)
        self.assertEqual({k: body["external_ref"][k] for k in ("lot_id", "plan_id")}, {"lot_id": str(lot_id), "plan_id": str(plan_id)})
        self.assertEqual(body["external_ref"].get("depot"), self.milestone.name)  # the lot's depot
        self.assertEqual(body["baseline"], {"source": "plan", "routes": [
            {"vehicle_type": "van", "package_ids": ["11", "12", "13"]}]})
        self.assertEqual(body["options"], {"recipe": "rapida", "label": "Lote 1"})
        self.assertTrue(key.startswith(f"lot-{lot_id}-plan-{plan_id}-"))
        self.assertEqual((out["optimization_id"], out["lot_id"], out["base_plan_id"]), ("bko_000000000001", lot_id, plan_id))
        row = self.db.get(BksOptimization, "bko_000000000001")
        self.assertEqual((row.company_id, row.delivery_lot_id, row.context_hash), (1, lot_id, "hash-1"))
        self._post(lot_id, options={"recipe": "rapida"}, label="Lote 1")  # same request again: same row
        self.assertEqual(len(self.db.exec(select(BksOptimization)).all()), 1)

    def test_needs_a_planned_lot_that_is_not_busy(self):
        lot_id = self._seed(DeliveryLotState.UNPROCESSED)
        with self.assertRaises(HTTPException) as e:
            self._post(lot_id)
        self.assertEqual(e.exception.status_code, 409)
        lot_id = self._seed(DeliveryLotState.PROCESSING)
        with self.assertRaises(HTTPException) as e:
            self._post(lot_id)
        self.assertEqual(e.exception.status_code, 409)

    def test_disabled_answers_404(self):
        lot_id, _ = self._processed_lot()
        with patch.object(bks_route.bks, "client", lambda: None), self.assertRaises(HTTPException) as e:
            self._post(lot_id)
        self.assertEqual(e.exception.status_code, 404)


class TestScope(_BksCase):
    def test_only_through_a_lot_of_the_callers_workspace(self):
        lot_id, _ = self._processed_lot()
        self._post(lot_id)
        other_lot, _ = self._processed_lot()
        for call in (lambda: bks_route.bks_optimizations_get(id=other_lot, optimization_id="bko_000000000001",
                                                             db=self.db, company_id=1),
                     lambda: bks_route.bks_optimizations_get(id=lot_id, optimization_id="bko_000000000001",
                                                             db=self.db, company_id=2)):
            with self.assertRaises(HTTPException) as e:
                call()
            self.assertEqual(e.exception.status_code, 404)
        items = bks_route.bks_optimizations_list(id=lot_id, db=self.db, company_id=1)["items"]
        self.assertEqual([i["optimization_id"] for i in items], ["bko_000000000001"])  # not another lot's


class TestSelect(_BksCase):
    def _select(self, lot_id):
        resp = bks_route.bks_optimizations_select(id=lot_id, optimization_id="bko_000000000001", solution_id="sol_3",
                                                  db=self.db, company_id=1)
        return resp.status_code, json.loads(resp.body)

    def test_a_picked_solution_becomes_the_lots_latest_plan(self):
        lot_id, base_plan = self._processed_lot()
        self._post(lot_id)
        status, plan = self._select(lot_id)
        self.assertEqual((status, plan["state"], plan["origin"]), (200, "PROCESSED", "bks"))
        self.assertEqual(plan["optimizer_session_id"], "bko_000000000001:sol_3")
        self.db.expire_all()
        lot = self.db.get(DeliveryLot, lot_id)
        self.assertEqual([p.origin for p in lot.plans], ["engine", "bks"])
        new = lot.plans[-1]
        self.assertEqual([p.route_data["vehicle_type"] for p in new.paths], ["van"])
        self.assertEqual([[str(d) for d in wp["delivery_ids"]] for wp in new.paths[0].route_data["optimized_waypoints"]
                          if wp.get("delivery_ids")], [["12"], ["11"]])
        row = self.db.get(BksOptimization, "bko_000000000001")
        self.assertEqual((row.selected_solution_id, row.result_plan_id, row.base_plan_id), ("sol_3", new.id, base_plan))
        self.assertIn(("select", 1, "bko_000000000001", "sol_3"), self.fake.calls)

    def test_a_lot_that_changed_cannot_take_the_solution(self):
        lot_id, _ = self._processed_lot()
        self._post(lot_id)
        self.assertFalse(bks_route.bks_optimizations_get(id=lot_id, optimization_id="bko_000000000001", db=self.db,
                                                         company_id=1)["stale"])
        self.digest = "hash-2"  # deliveries, fleet or limits changed
        self.assertTrue(bks_route.bks_optimizations_get(id=lot_id, optimization_id="bko_000000000001", db=self.db,
                                                        company_id=1)["stale"])
        with self.assertRaises(HTTPException) as e:
            self._select(lot_id)
        self.assertEqual((e.exception.status_code, e.exception.detail["code"]), (409, "lot_changed"))

    def test_upstream_errors_keep_their_meaning_and_nothing_is_stored(self):
        lot_id, _ = self._processed_lot()
        self._post(lot_id)
        self.fake.fail = ("routes", BksOptimizerError("ya no", status=410, code="solution_expired"))
        with self.assertRaises(HTTPException) as e:
            self._select(lot_id)
        self.assertEqual((e.exception.status_code, e.exception.detail["code"]), (410, "solution_expired"))
        self.fake.fail = ("select", BksOptimizerError("caído", status=503))
        with self.assertRaises(HTTPException) as e:
            self._select(lot_id)
        self.assertEqual(e.exception.status_code, 502)
        self.db.expire_all()
        self.assertEqual([p.origin for p in self.db.get(DeliveryLot, lot_id).plans], ["engine"])  # rolled back


class TestClient(unittest.TestCase):
    def test_headers_and_service_errors(self):
        seen = []

        def handler(request):
            seen.append(request)
            if request.url.path.endswith("/routes"):
                return httpx.Response(410, json={"error": {"code": "solution_expired", "message": "ya no",
                                                           "details": None}})
            return httpx.Response(202, json={"optimization_id": "bko_1"})
        client = BksOptimizer("http://bks:8815/", "clave", transport=httpx.MockTransport(handler))
        self.assertEqual(client.submit(7, {"x": 1}, "k-1"), {"optimization_id": "bko_1"})
        r = seen[0]
        self.assertEqual((str(r.url), r.headers["Authorization"], r.headers["X-Vepathos-Company-Id"],
                          r.headers["Idempotency-Key"]), ("http://bks:8815/v1/bks-optimizations", "Bearer clave", "7", "k-1"))
        with self.assertRaises(BksOptimizerError) as e:
            client.routes(7, "bko_1", "sol_1")
        self.assertEqual((e.exception.status, e.exception.code, str(e.exception)), (410, "solution_expired", "ya no"))

    def test_unreachable_is_an_error_without_status(self):
        def handler(request):
            raise httpx.ConnectError("no route")
        with self.assertRaises(BksOptimizerError) as e:
            BksOptimizer("http://bks", "k", transport=httpx.MockTransport(handler)).get(1, "bko_1")
        self.assertIsNone(e.exception.status)
