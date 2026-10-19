"""Plan the engine could not route (status=failed + message + error_code).

GET /lots/{id}/plan must stop showing it as processing: CANCELED plus an `error`
that later reads still return. A failed reoptimize keeps the old routes (PROCESSED)
and reports the same `error` on that read only.
"""
import json
import os
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("RDBMS_URL", "sqlite://")

from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, Session, create_engine

# Import model modules so every table is registered on SQLModel.metadata.
import models.company  # noqa: F401
import models.tenant  # noqa: F401
import models.driver  # noqa: F401
import models.vehicle  # noqa: F401
from models.delivery_lot import DeliveryLot
from models.delivery_plan import DeliveryPath, DeliveryPlan
from models.enum import DeliveryLotState
from models.fleet import Fleet
from models.milestone import Milestone

from libs.optimizer.models import ResultSet
from libs.optimizer.optimizer import Optimizer
import routes.delivery_lots as lots_route

FAILED_BODY = {
    "session_id": "sess-1",
    "status": "failed",
    "message": "The delivery area is too large to route as one plan",
    "error_code": "area_too_large",
}


def _make_session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def _response(resp) -> tuple[int, dict]:
    return resp.status_code, json.loads(resp.body)


class FakeOptimizer:
    def __init__(self, plan_result=None, draft_result=None, route_status=None):
        self.plan_result = plan_result
        self.draft_result = draft_result
        self.route_status = route_status

    def get_plan_result(self, task_id):
        return self.plan_result

    def get_draft_result(self, task_id):
        return self.draft_result

    def get_route_status(self, session_id):
        return self.route_status


class TestGetPlanResultHonorsFailed(unittest.TestCase):
    def _get(self, status_code, body):
        r = MagicMock()
        r.status_code = status_code
        r.text = json.dumps(body)
        with patch("libs.optimizer.optimizer.requests.get", return_value=r):
            return Optimizer("http://optimizer", 8000, "k").get_plan_result("sess-1")

    def test_failed_body_is_failed_with_reason(self):
        result = self._get(200, FAILED_BODY)
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.error_code, "area_too_large")
        self.assertEqual(result.message, FAILED_BODY["message"])
        self.assertIsNone(result.routes)

    def test_completed_body_stays_completed(self):
        result = self._get(200, {"session_id": "sess-1", "status": "completed", "routes": []})
        self.assertEqual(result.status, "completed")
        # Legacy body without a status marker: still completed, as before.
        result = self._get(200, {"session_id": "sess-1", "routes": []})
        self.assertEqual(result.status, "completed")

    def test_non_200_stays_processing(self):
        self.assertEqual(self._get(202, {"detail": "processing"}).status, "processing")

    def test_draft_failure_carries_reason(self):
        r = MagicMock()
        r.status_code = 200
        r.text = json.dumps({**FAILED_BODY, "error_code": "country_route_unavailable"})
        with patch("libs.optimizer.optimizer.requests.get", return_value=r):
            result = Optimizer("http://optimizer", 8000, "k").get_draft_result("sess-1")
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.error_code, "country_route_unavailable")


class _LotPlanCase(unittest.TestCase):
    def setUp(self):
        self.db = _make_session()
        self.milestone = Milestone(name="Depot", location="-34.6,-58.4", company_id=1)
        self.fleet = Fleet(name="Fleet", company_id=1)
        self.db.add(self.milestone)
        self.db.add(self.fleet)
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def _seed(self, state, with_path=False):
        lot = DeliveryLot(
            company_id=1,
            state=state,
            milestone_id=self.milestone.id,
            fleet_id=self.fleet.id,
        )
        self.db.add(lot)
        self.db.commit()
        plan = DeliveryPlan(delivery_lot_id=lot.id, optimizer_id="sess-1")
        self.db.add(plan)
        self.db.commit()
        if with_path:
            self.db.add(DeliveryPath(
                delivery_plan_id=plan.id,
                milestone_id=self.milestone.id,
                route_data={"route_index": 0, "route_id": "old"},
            ))
            self.db.commit()
        return lot.id

    def _get_plan(self, lot_id, fake):
        with patch.object(lots_route, "optimizer", fake):
            return _response(lots_route.delivery_lots_id_plan_get(id=lot_id, db=self.db, company_id=1))

    def _get_status(self, lot_id, fake):
        with patch.object(lots_route, "optimizer", fake):
            return _response(
                lots_route.delivery_lots_id_plan_status_get(id=lot_id, db=self.db, company_id=1)
            )

    def _state(self, lot_id):
        self.db.expire_all()
        return self.db.get(DeliveryLot, lot_id).state


class TestProcessingFailure(_LotPlanCase):
    def test_failed_plan_is_canceled_with_error_and_reread_keeps_it(self):
        lot_id = self._seed(DeliveryLotState.PROCESSING)
        fake = FakeOptimizer(plan_result=ResultSet.model_validate(FAILED_BODY))

        status, body = self._get_plan(lot_id, fake)
        expected = {
            "state": "CANCELED",
            "routes": None,
            "session_id": "sess-1",
            "optimizer_session_id": "sess-1",
            "error": {"code": "area_too_large", "message": FAILED_BODY["message"]},
        }
        self.assertEqual(status, 200)
        self.assertEqual(body, expected)
        self.assertEqual(self._state(lot_id), DeliveryLotState.CANCELED)

        # Later read: the engine is not asked again, the stored reason is returned.
        status, again = self._get_plan(lot_id, FakeOptimizer())
        self.assertEqual(status, 200)
        self.assertEqual(again, expected)

        # The status poll still answers with the code once the lot left PROCESSING.
        status, polled = self._get_status(lot_id, FakeOptimizer())
        self.assertEqual(status, 410)
        self.assertEqual(polled, {"detail": FAILED_BODY["message"], "error_code": "area_too_large"})

    def test_failed_without_code_defaults_to_plan_failed(self):
        lot_id = self._seed(DeliveryLotState.PROCESSING)
        fake = FakeOptimizer(plan_result=ResultSet(status="failed", message="Route optimization failed"))
        _, body = self._get_plan(lot_id, fake)
        self.assertEqual(body["error"], {"code": "plan_failed", "message": "Route optimization failed"})

    def test_processing_unchanged(self):
        lot_id = self._seed(DeliveryLotState.PROCESSING)
        status, body = self._get_plan(lot_id, FakeOptimizer(plan_result=ResultSet(status="processing")))
        self.assertEqual(status, 200)
        self.assertEqual(body, {
            "state": "PROCESSING",
            "routes": None,
            "session_id": "sess-1",
            "optimizer_session_id": "sess-1",
        })
        self.assertEqual(self._state(lot_id), DeliveryLotState.PROCESSING)

    def test_completed_unchanged(self):
        lot_id = self._seed(DeliveryLotState.PROCESSING)
        fake = FakeOptimizer(plan_result=ResultSet(
            status="completed",
            routes=[],
            totals={"total_routes": 0, "total_points": 0},
        ))
        status, body = self._get_plan(lot_id, fake)
        self.assertEqual(status, 200)
        self.assertEqual(body["state"], "PROCESSED")
        self.assertNotIn("error", body)
        self.assertEqual(body["totals"], {"total_routes": 0, "total_points": 0})
        self.assertEqual(self._state(lot_id), DeliveryLotState.PROCESSED)

    def test_status_relays_engine_410_with_error_code(self):
        lot_id = self._seed(DeliveryLotState.PROCESSING)
        engine_body = {"detail": FAILED_BODY["message"], "error_code": "area_too_large"}
        status, body = self._get_status(lot_id, FakeOptimizer(route_status=(410, engine_body)))
        self.assertEqual(status, 410)
        self.assertEqual(body, engine_body)


class TestOptimizingFailure(_LotPlanCase):
    def test_failed_reoptimize_keeps_old_routes_and_reports_error_once(self):
        lot_id = self._seed(DeliveryLotState.OPTIMIZING, with_path=True)
        fake = FakeOptimizer(draft_result=ResultSet.model_validate(
            {**FAILED_BODY, "error_code": "country_route_unavailable"}
        ))

        status, body = self._get_plan(lot_id, fake)
        self.assertEqual(status, 200)
        self.assertEqual(body["state"], "PROCESSED")
        self.assertEqual([r["route_id"] for r in body["routes"]], ["old"])
        self.assertEqual(body["error"], {
            "code": "country_route_unavailable",
            "message": FAILED_BODY["message"],
        })
        self.assertEqual(self._state(lot_id), DeliveryLotState.PROCESSED)

        # Not stored as a lot failure: the next read is the plain PROCESSED plan.
        _, again = self._get_plan(lot_id, FakeOptimizer())
        self.assertEqual(again["state"], "PROCESSED")
        self.assertNotIn("error", again)
        self.assertEqual([r["route_id"] for r in again["routes"]], ["old"])


if __name__ == "__main__":
    unittest.main()
