import os
import unittest

os.environ.setdefault("RDBMS_URL", "sqlite://")

from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, Session, create_engine, select

import models.company  # noqa: F401
import models.tenant  # noqa: F401
import models.api_key  # noqa: F401
from models.api_key import ApiKey
from models.company import Company
from models.tenant import Tenant

from libs.authorization.authorization import authorization, hash_api_key, API_KEY_PREFIX
from libs.tenant.context import DEFAULT_TENANT_ALIAS, get_company_for_tenant, get_product_tenant


def _creds(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


def _make_session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    session = Session(engine)
    session.add(Tenant(id=1, alias="client-web"))
    session.add(Company(id=1, tenant_id=1, alias="vepathos-web-client"))
    session.add(Company(id=42, tenant_id=1, alias="user-workspace"))
    session.commit()
    return session


class TestApiKeyHashing(unittest.TestCase):
    def test_hash_is_deterministic_and_not_the_key(self):
        key = f"{API_KEY_PREFIX}secret-value"
        self.assertEqual(hash_api_key(key), hash_api_key(key))
        self.assertNotIn("secret-value", hash_api_key(key))
        self.assertEqual(len(hash_api_key(key)), 64)  # sha256 hex


class TestApiKeyAuthorization(unittest.TestCase):
    def setUp(self):
        self.db = _make_session()
        self.raw = f"{API_KEY_PREFIX}company42key"
        self.db.add(
            ApiKey(
                company_id=42,
                name="test app",
                key_prefix=self.raw[:12],
                key_hash=hash_api_key(self.raw),
            )
        )
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def test_valid_key_resolves_company(self):
        self.assertEqual(authorization(self.db, _creds(self.raw)), 42)

    def test_missing_credentials_is_401(self):
        with self.assertRaises(HTTPException) as ctx:
            authorization(self.db, None)
        self.assertEqual(ctx.exception.status_code, 401)

    def test_unknown_key_is_401(self):
        with self.assertRaises(HTTPException) as ctx:
            authorization(self.db, _creds(f"{API_KEY_PREFIX}nope"))
        self.assertEqual(ctx.exception.status_code, 401)

    def test_revoked_key_is_401(self):
        from datetime import datetime, timezone

        row = self.db.exec(
            select(ApiKey).where(ApiKey.company_id == 42)
        ).first()
        row.revoked_at = datetime.now(timezone.utc)
        self.db.add(row)
        self.db.commit()
        with self.assertRaises(HTTPException) as ctx:
            authorization(self.db, _creds(self.raw))
        self.assertEqual(ctx.exception.status_code, 401)


class TestProductTenant(unittest.TestCase):
    def setUp(self):
        self.db = _make_session()
        os.environ["ROUTEHUB_TENANT_ALIAS"] = "client-web"

    def tearDown(self):
        self.db.close()
        os.environ.pop("ROUTEHUB_TENANT_ALIAS", None)

    def test_default_tenant_alias(self):
        self.assertEqual(DEFAULT_TENANT_ALIAS, "client-web")

    def test_product_tenant_loaded_from_db(self):
        self.assertEqual(get_product_tenant(self.db).alias, "client-web")

    def test_company_must_belong_to_product_tenant(self):
        self.db.add(Tenant(id=2, alias="other-product"))
        self.db.add(Company(id=99, tenant_id=2, alias="foreign"))
        self.db.commit()
        tenant = get_product_tenant(self.db)
        with self.assertRaises(HTTPException) as ctx:
            get_company_for_tenant(self.db, 99, tenant.id)
        self.assertEqual(ctx.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
