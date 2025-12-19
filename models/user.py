from sqlmodel import (
    Field,
    SQLModel,
)
from .company import Company

class User(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    alias: str
    company_id: int = Field(foreign_key="company.id")
