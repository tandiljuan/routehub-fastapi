from sqlmodel import (
    Field,
    SQLModel,
)

class Tenant(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    alias: str
