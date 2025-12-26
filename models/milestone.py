from sqlmodel import (
    Column,
    Enum,
    Field,
    SQLModel,
)
from .enum import MilestoneCategory

class MilestoneBase(SQLModel):
    name: str
    location: str
    category: MilestoneCategory | None = Field(default=None, sa_column=Column(Enum(MilestoneCategory)))

class MilestoneCreate(MilestoneBase):
    pass
