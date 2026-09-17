import os
import unittest

os.environ.setdefault("RDBMS_URL", "sqlite://")

from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, Session, create_engine, select

import models.company  # noqa: F401
import models.vehicle  # noqa: F401
from models.vehicle import Vehicle

from libs.rls import (
    RLS_SETTING,
    apply_company_to_session,
    clear_current_company,
    set_current_company,
    _current_company,
)


class TestRlsContextVar(unittest.TestCase):
    def tearDown(self):
        clear_current_company()

    def test_set_and_clear(self):
        set_current_company(7)
        self.assertEqual(_current_company.get(), 7)
        clear_current_company()
        self.assertIsNone(_current_company.get())

    def test_setting_name(self):
        self.assertEqual(RLS_SETTING, "app.current_company")


class TestRlsNoOpOnSqlite(unittest.TestCase):
    def test_apply_is_a_harmless_noop_off_postgres(self):
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        SQLModel.metadata.create_all(engine)
        with Session(engine) as session:
            session.add(Vehicle(company_id=1, name="x"))
            session.commit()
            # Must not raise on SQLite (no set_config / no RLS).
            apply_company_to_session(session, 1)
            rows = session.exec(select(Vehicle)).all()
            self.assertEqual(len(rows), 1)


if __name__ == "__main__":
    unittest.main()
