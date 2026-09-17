"""Row-level security enforcement tests — require a real Postgres.

These are SKIPPED unless RLS_TEST_DATABASE_URL points to a *superuser* Postgres
connection (used to create a throwaway db + a restricted role). Example:

    RLS_TEST_DATABASE_URL="postgresql://routehub_user:routehub_pass@localhost:5433/postgres" \\
        python -m pytest tests/test_rls_postgres.py -v

What is validated:
  * fail-closed when app.current_company is unset
  * a restricted role sees only its company's rows (cross-company read = 0)
  * WITH CHECK blocks writing rows into another company
  * a SUPERUSER role BYPASSES RLS (the critical operational caveat)
  * the app request path (API key -> GUC) scopes queries end to end
"""

import os
import unittest
import uuid

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool

os.environ.setdefault("RDBMS_URL", "sqlite://")

ADMIN_URL = os.environ.get("RLS_TEST_DATABASE_URL")
APP_ROLE = "rh_rls_test"
APP_PASSWORD = "rls_test_pass"
MIGRATION = os.environ.get(
    "RLS_MIGRATION_SQL",
    os.path.normpath(
        os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "..",
            "routehub-dbschem",
            "migrations",
            "20260702192100_row_level_security.sql",
        )
    ),
)

_state: dict = {}


def _admin_can_connect() -> bool:
    if not ADMIN_URL:
        return False
    try:
        eng = create_engine(ADMIN_URL, poolclass=NullPool)
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))
        eng.dispose()
        return True
    except Exception:
        return False


def setUpModule():
    if not _admin_can_connect():
        raise unittest.SkipTest(
            "Set RLS_TEST_DATABASE_URL to a superuser Postgres URL to run RLS tests"
        )

    from sqlmodel import SQLModel

    # Register every table on the metadata.
    import models.api_key  # noqa: F401
    import models.company  # noqa: F401
    import models.tenant  # noqa: F401
    import models.vehicle  # noqa: F401
    import models.driver  # noqa: F401
    import models.fleet  # noqa: F401
    import models.milestone  # noqa: F401
    import models.delivery  # noqa: F401
    import models.delivery_lot  # noqa: F401
    import models.delivery_plan  # noqa: F401
    from libs.authorization.authorization import API_KEY_PREFIX, hash_api_key

    admin_url = make_url(ADMIN_URL)
    db_name = f"rls_test_{uuid.uuid4().hex[:8]}"

    # 1) Create the throwaway database + restricted role (AUTOCOMMIT for CREATE DB).
    maint = create_engine(admin_url.set(database="postgres"), poolclass=NullPool)
    with maint.connect() as conn:
        conn = conn.execution_options(isolation_level="AUTOCOMMIT")
        conn.execute(text(f'CREATE DATABASE "{db_name}"'))
        conn.execute(text(f"DROP ROLE IF EXISTS {APP_ROLE}"))
        conn.execute(
            text(f"CREATE ROLE {APP_ROLE} LOGIN PASSWORD '{APP_PASSWORD}' "
                 "NOSUPERUSER NOBYPASSRLS")
        )
    maint.dispose()

    # Track what exists so teardown runs even if the rest of setup fails.
    _state.update(db_name=db_name, admin_url=admin_url)

    try:
        # 2) Owner connection: schema, RLS migration, grants, seed.
        owner_url = admin_url.set(database=db_name)
        owner = create_engine(owner_url, poolclass=NullPool)
        _state["owner"] = owner
        SQLModel.metadata.create_all(owner)
        with open(MIGRATION) as fh:
            migration_sql = fh.read()
        raw_key = f"{API_KEY_PREFIX}rls-e2e-key"

        # Raw psycopg cursor: the migration contains `%I`/`%s` (plpgsql format())
        # and no-param statements, both of which trip SQLAlchemy's param handling.
        raw = owner.raw_connection()
        try:
            cur = raw.cursor()
            cur.execute(migration_sql)
            cur.execute(f"GRANT USAGE ON SCHEMA public TO {APP_ROLE}")
            cur.execute(
                f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {APP_ROLE}"
            )
            cur.execute(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {APP_ROLE}")
            cur.execute("INSERT INTO tenant (id, alias) VALUES (1, 'client-web') ON CONFLICT DO NOTHING")
            cur.execute(
                "INSERT INTO company (id, tenant_id, alias) VALUES "
                "(1, 1, 'c1'), (2, 1, 'c2') ON CONFLICT DO NOTHING"
            )
            cur.execute(
                "INSERT INTO vehicle (id, company_id, name) VALUES "
                "(10, 1, 'mine'), (20, 2, 'theirs') ON CONFLICT DO NOTHING"
            )
            cur.execute(
                "INSERT INTO api_key (company_id, name, key_prefix, key_hash, created_at) "
                f"VALUES (1, 'e2e', '{raw_key[:12]}', '{hash_api_key(raw_key)}', now())"
            )
            raw.commit()
        finally:
            raw.close()

        _state["app_engine"] = create_engine(
            owner_url.set(username=APP_ROLE, password=APP_PASSWORD), poolclass=NullPool
        )
        _state["raw_key"] = raw_key
    except Exception:
        tearDownModule()  # never leak the throwaway db/role on a setup failure
        raise


def tearDownModule():
    if not _state.get("db_name"):
        return
    for key in ("owner", "app_engine"):
        engine = _state.get(key)
        if engine is not None:
            engine.dispose()
    maint = create_engine(_state["admin_url"].set(database="postgres"), poolclass=NullPool)
    with maint.connect() as conn:
        conn = conn.execution_options(isolation_level="AUTOCOMMIT")
        conn.execute(text(f'DROP DATABASE IF EXISTS "{_state["db_name"]}" WITH (FORCE)'))
        conn.execute(text(f"DROP ROLE IF EXISTS {APP_ROLE}"))
    maint.dispose()
    _state.clear()


def _scope(conn, company_id):
    conn.execute(text(f"SELECT set_config('app.current_company', '{company_id}', false)"))


def _vehicle_ids(conn, company_id=None):
    if company_id is not None:
        _scope(conn, company_id)
    return [r[0] for r in conn.execute(text("SELECT id FROM vehicle ORDER BY id"))]


class TestRlsEnforcement(unittest.TestCase):
    """Restricted role (NOBYPASSRLS): the policy must hold."""

    def test_fail_closed_when_company_unset(self):
        with _state["app_engine"].connect() as conn:
            ids = [r[0] for r in conn.execute(text("SELECT id FROM vehicle"))]
            self.assertEqual(ids, [])

    def test_scoped_to_company_1(self):
        with _state["app_engine"].connect() as conn:
            self.assertEqual(_vehicle_ids(conn, 1), [10])

    def test_scoped_to_company_2(self):
        with _state["app_engine"].connect() as conn:
            self.assertEqual(_vehicle_ids(conn, 2), [20])

    def test_cannot_read_other_company_by_id(self):
        with _state["app_engine"].connect() as conn:
            _scope(conn, 1)
            count = conn.execute(text("SELECT count(*) FROM vehicle WHERE id = 20")).scalar()
            self.assertEqual(count, 0)

    def test_with_check_blocks_foreign_insert(self):
        from sqlalchemy.exc import ProgrammingError, IntegrityError

        with _state["app_engine"].connect() as conn:
            _scope(conn, 2)
            with self.assertRaises((ProgrammingError, IntegrityError)):
                conn.execute(text("INSERT INTO vehicle (company_id, name) VALUES (1, 'evil')"))


class TestSuperuserBypass(unittest.TestCase):
    """Documents the caveat: a superuser ignores RLS — the app must NOT use one."""

    def test_superuser_sees_all_companies(self):
        with _state["owner"].connect() as conn:
            self.assertEqual(_vehicle_ids(conn, 1), [10, 20])


class TestAppRequestScoping(unittest.TestCase):
    """End to end: API key -> GUC -> scoped queries through the real app."""

    def setUp(self):
        import main
        from models.database import get_session
        from sqlmodel import Session
        from libs.rls import clear_current_company

        self.main = main

        def _override():
            with Session(_state["app_engine"]) as session:
                try:
                    yield session
                finally:
                    clear_current_company()

        main.app.dependency_overrides[get_session] = _override
        from fastapi.testclient import TestClient

        self.client = TestClient(main.app)
        self.headers = {"Authorization": f"Bearer {_state['raw_key']}"}

    def tearDown(self):
        self.main.app.dependency_overrides.clear()

    def test_request_without_key_is_401(self):
        self.assertEqual(self.client.get("/vehicles").status_code, 401)

    def test_request_is_scoped_to_key_company(self):
        r = self.client.get("/vehicles", headers=self.headers)
        self.assertEqual(r.status_code, 200)
        self.assertEqual([str(v["id"]) for v in r.json()], ["10"])

    def test_cross_company_get_by_id_is_404(self):
        self.assertEqual(
            self.client.get("/vehicles/20", headers=self.headers).status_code, 404
        )

    def test_own_get_by_id_is_200(self):
        self.assertEqual(
            self.client.get("/vehicles/10", headers=self.headers).status_code, 200
        )


if __name__ == "__main__":
    unittest.main()
