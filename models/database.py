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
RDBMS_LOG = str(os.environ.get("RDBMS_LOG")).lower()
RDBMS_LOG = True if RDBMS_LOG not in ["", "0", "off", "false", "null", "none"] else False

IS_SQLITE = True if "sqlite" in RDBMS_URL else False

# Connection arguments for SQLite with multi-threading FastAPI
connect_args = {"check_same_thread": False} if IS_SQLITE else {}

# Create the engine.
# Set `echo=True` to display SQL queries in the console.
engine = create_engine(
    RDBMS_URL,
    echo=RDBMS_LOG,
    connect_args=connect_args,
)

if IS_SQLITE:
    with engine.connect() as connection:
        connection.execute(text("PRAGMA foreign_keys=ON"))

def get_engine():
    return engine

def get_session():
    with SQLModel_Session(engine) as session:
        yield session

# Type alias for route definitions
Session = Annotated[SQLModel_Session, Depends(get_session)]
