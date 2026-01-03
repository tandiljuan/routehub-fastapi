import os
from typing import Annotated
from fastapi import Depends
from sqlmodel import SQLModel
from sqlmodel import Session as SQLModel_Session
from sqlmodel import create_engine

RDBMS_URL = os.environ.get("RDBMS_URL")
RDBMS_USR = os.environ.get("RDBMS_USR")
RDBMS_PWD = os.environ.get("RDBMS_PWD")

connect_args = {}

# Connection arguments for SQLite with multi-threading FastAPI
if "sqlite" in RDBMS_URL:
    connect_args = {"check_same_thread": False}

# Create the engine.
# Set `echo=True` to display SQL queries in the console.
engine = create_engine(
    RDBMS_URL,
    echo=True,
    connect_args=connect_args,
)

def get_engine():
    return engine

def get_session():
    with SQLModel_Session(engine) as session:
        yield session

# Type alias for route definitions
Session = Annotated[SQLModel_Session, Depends(get_session)]
