from sqlmodel import (
    Field,
    SQLModel,
)

class Company(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    tenant_id: int
    alias: str
