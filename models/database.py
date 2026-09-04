import logging
import os
from typing import Annotated
from fastapi import Depends
from sqlmodel import (
    SQLModel,
    Session as SQLModel_Session,
    create_engine,
    text,
)

RDBMS_URL = os.environ.get("RDBMS_URL")
# Opt-in only: unset / falsey keeps the console readable. Set RDBMS_LOG=true
# when you actually need SQLAlchemy echo (full SQL + bind params).
_RDBMS_LOG_RAW = str(os.environ.get("RDBMS_LOG") or "").strip().lower()
RDBMS_LOG = _RDBMS_LOG_RAW in {"1", "true", "on", "yes"}

IS_SQLITE = True if "sqlite" in RDBMS_URL else False

if not RDBMS_LOG:
    # Engine echo also attaches handlers; silence leftover noise when off.
    for _name in (
        "sqlalchemy.engine",
        "sqlalchemy.engine.Engine",
        "sqlalchemy.pool",
        "sqlalchemy.dialects",
    ):
        logging.getLogger(_name).setLevel(logging.WARNING)

# Connection arguments for SQLite with multi-threading FastAPI
connect_args = {"check_same_thread": False} if IS_SQLITE else {}


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


# Sync routes run in the threadpool (see routes/*.py), so up to
# THREADPOOL_LIMIT requests hit the pool at once per worker. Keep the pool at
# least that big or threads queue 30s on a connection and time out; keep it no
# bigger than needed, because api-prod shares one Postgres with api-doc and
# every connection costs backend memory there.
#
# Budget per deployment (api-prod is a shared 4 vCPU / 8 GB box):
#   connections = UVICORN_WORKERS * (POOL_SIZE + MAX_OVERFLOW) <= PG max_connections
pool_kwargs = (
    {}
    if IS_SQLITE
    else {
        "pool_size": _int_env("RDBMS_POOL_SIZE", 10),
        "max_overflow": _int_env("RDBMS_MAX_OVERFLOW", 5),
        # Postgres/proxies drop idle connections; without pre_ping the first
        # query on a stale one fails instead of transparently reconnecting.
        "pool_pre_ping": True,
        "pool_recycle": _int_env("RDBMS_POOL_RECYCLE", 1800),
    }
)

# Create the engine.
# Set `echo=True` to display SQL queries in the console.
engine = create_engine(
    RDBMS_URL,
    echo=RDBMS_LOG,
    connect_args=connect_args,
    **pool_kwargs,
)

if IS_SQLITE:
    with engine.connect() as connection:
        connection.execute(text("PRAGMA foreign_keys=ON"))

def get_engine():
    return engine

def get_session():
    with SQLModel_Session(engine) as session:
        try:
            yield session
        finally:
            # Drop the per-request company so a pooled connection/thread can't
            # carry it into the next request (RLS defense-in-depth hygiene).
            from libs.rls import clear_current_company

            clear_current_company()

# Type alias for route definitions
Session = Annotated[SQLModel_Session, Depends(get_session)]
