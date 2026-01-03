from pydantic import field_serializer
from sqlmodel import (
    Column,
    Enum,
    Field,
    SQLModel,
)
from .enum import MilestoneCategory
from .company import Company

class MilestoneBase(SQLModel):
    name: str
    location: str
    category: MilestoneCategory | None = Field(default=None, sa_column=Column(Enum(MilestoneCategory)))

class MilestoneCreate(MilestoneBase):
    pass

class MilestoneUpdate(MilestoneCreate):
    name: str | None = None
    location: str | None = None

class MilestoneResponse(MilestoneCreate):
    id: str | int

    @field_serializer('id', when_used='json')
    def serialize_id_to_str(self, id: int):
        return str(id)

class Milestone(MilestoneBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    company_id: int = Field(foreign_key="company.id")
