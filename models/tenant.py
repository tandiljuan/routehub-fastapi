from sqlmodel import Field, SQLModel


class Tenant(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    alias: str = Field(max_length=50, unique=True)
