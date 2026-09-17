import os
import unittest

os.environ.setdefault("RDBMS_URL", "sqlite://")

from fastapi import HTTPException
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, Session, create_engine

# Import model modules so every table is registered on SQLModel.metadata.
import models.company  # noqa: F401
import models.tenant  # noqa: F401
import models.milestone  # noqa: F401
import models.driver  # noqa: F401
import models.fleet  # noqa: F401
import models.vehicle  # noqa: F401
import models.delivery_plan  # noqa: F401
from models.delivery import Delivery
from models.delivery_lot import DeliveryLot, DeliveryLotDelivery

from libs.lot_persistence import bulk_link_lot_deliveries, replace_lot_deliveries
from libs.tenant.context import assert_company_match


def _make_session() -> Session:
    # Shared in-memory DB (StaticPool) without FK enforcement: we only seed the
    # rows the scoping logic actually reads.
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return Session(engine)


class TestAssertCompanyMatch(unittest.TestCase):
    def test_missing_resource_is_404(self):
        with self.assertRaises(HTTPException) as ctx:
            assert_company_match(None, 1, "Driver")
        self.assertEqual(ctx.exception.status_code, 404)

    def test_cross_tenant_resource_is_404_not_403(self):
        # 404 (not 403) so a foreign id is indistinguishable from a missing one.
        foreign = DeliveryLot(company_id=2)
        with self.assertRaises(HTTPException) as ctx:
            assert_company_match(foreign, 1, "Delivery lot")
        self.assertEqual(ctx.exception.status_code, 404)

    def test_same_company_passes(self):
        owned = DeliveryLot(company_id=1)
        assert_company_match(owned, 1, "Delivery lot")  # does not raise


class TestBulkLinkCompanyScoping(unittest.TestCase):
    def setUp(self):
        self.db = self.session = _make_session()
        self.mine = Delivery(destination="+0-0", company_id=1, milestone_id=1)
        self.theirs = Delivery(destination="+0-0", company_id=2, milestone_id=1)
        self.db.add(self.mine)
        self.db.add(self.theirs)
        self.db.commit()
        self.db.refresh(self.mine)
        self.db.refresh(self.theirs)

    def tearDown(self):
        self.db.close()

    def _linked_ids(self, lot_id: int) -> set[int]:
        from sqlmodel import select

        return set(
            self.db.exec(
                select(DeliveryLotDelivery.delivery_id).where(
                    DeliveryLotDelivery.delivery_lot_id == lot_id
                )
            ).all()
        )

    def test_company_filter_skips_other_tenant(self):
        ids = [str(self.mine.id), str(self.theirs.id)]
        linked = bulk_link_lot_deliveries(self.db, 99, ids, company_id=1)
        self.db.commit()
        self.assertEqual(linked, 1)
        self.assertEqual(self._linked_ids(99), {self.mine.id})

    def test_without_company_links_all(self):
        ids = [str(self.mine.id), str(self.theirs.id)]
        linked = bulk_link_lot_deliveries(self.db, 98, ids)
        self.db.commit()
        self.assertEqual(linked, 2)

    def test_replace_is_also_scoped(self):
        replace_lot_deliveries(
            self.db, 97, [str(self.mine.id), str(self.theirs.id)], company_id=1
        )
        self.db.commit()
        self.assertEqual(self._linked_ids(97), {self.mine.id})


if __name__ == "__main__":
    unittest.main()
