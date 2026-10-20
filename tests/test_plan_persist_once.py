"""Two polls of the same finished lot must store its routes once (lot 201: 46 paths for 23 routes).

GET /lots/{id}/plan reads PROCESSING, asks the optimizer, and only then writes the routes. If
another poll finished meanwhile, the lot is already PROCESSED with its routes: this poll must read
them, not clear + insert again.
"""
from sqlmodel import select

from libs.optimizer.models import ResultSet
from models.delivery_lot import DeliveryLot
from models.delivery_plan import DeliveryPath, DeliveryPlan
from models.enum import DeliveryLotState
from tests.test_plan_failure import FakeOptimizer, _LotPlanCase


class _RacingOptimizer(FakeOptimizer):
    """While this poll waits on the optimizer, the other poll stores the result."""

    def __init__(self, db, lot_id, result, final_state):
        super().__init__(plan_result=result, draft_result=result)
        self.db, self.lot_id, self.final_state = db, lot_id, final_state

    def _other_poll_finishes(self):
        lot = self.db.get(DeliveryLot, self.lot_id)
        plan = self.db.exec(select(DeliveryPlan).where(DeliveryPlan.delivery_lot_id == self.lot_id)).first()
        self.db.add(DeliveryPath(delivery_plan_id=plan.id, milestone_id=lot.milestone_id,
                                 route_data={"route_index": 0, "route_id": "stored-by-other-poll"}))
        lot.state = self.final_state
        self.db.add(lot)
        self.db.commit()

    def get_plan_result(self, task_id):
        self._other_poll_finishes()
        return self.plan_result

    def get_draft_result(self, task_id):
        self._other_poll_finishes()
        return self.draft_result


COMPLETED = ResultSet(status="completed", routes=[], totals={"total_routes": 1, "total_points": 1})


class TestPersistOnce(_LotPlanCase):
    def _paths(self, lot_id):
        self.db.expire_all()
        plan = self.db.exec(select(DeliveryPlan).where(DeliveryPlan.delivery_lot_id == lot_id)).first()
        return [p.route_data["route_id"] for p in
                self.db.exec(select(DeliveryPath).where(DeliveryPath.delivery_plan_id == plan.id)).all()]

    def test_a_poll_that_lost_the_race_reads_the_stored_routes(self):
        lot_id = self._seed(DeliveryLotState.PROCESSING)
        status, body = self._get_plan(lot_id, _RacingOptimizer(self.db, lot_id, COMPLETED, DeliveryLotState.PROCESSED))
        self.assertEqual(status, 200)
        self.assertEqual(body["state"], "PROCESSED")
        self.assertEqual(self._paths(lot_id), ["stored-by-other-poll"])     # not cleared, not doubled

    def test_a_reoptimize_already_applied_is_not_applied_again(self):
        lot_id = self._seed(DeliveryLotState.OPTIMIZING)
        status, body = self._get_plan(lot_id, _RacingOptimizer(self.db, lot_id, COMPLETED, DeliveryLotState.PROCESSED))
        self.assertEqual(status, 200)
        self.assertEqual(self._paths(lot_id), ["stored-by-other-poll"])

    def test_a_single_poll_still_stores_the_result(self):
        lot_id = self._seed(DeliveryLotState.PROCESSING)
        status, body = self._get_plan(lot_id, FakeOptimizer(plan_result=COMPLETED))
        self.assertEqual(body["state"], "PROCESSED")
        self.assertEqual(self._state(lot_id), DeliveryLotState.PROCESSED)
