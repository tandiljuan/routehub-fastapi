from pydantic import field_serializer
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

class MilestoneResponse(MilestoneCreate):
    id: str | int

    @field_serializer('id', when_used='json')
    def serialize_id_to_str(self, id: int):
        return str(id)
