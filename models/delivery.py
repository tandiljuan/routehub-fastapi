from typing import Any
from pydantic import (
    SerializerFunctionWrapHandler as sfWrapHandler,
    field_serializer,
    model_serializer,
)
from sqlmodel import (
    Column,
    Enum,
    Field,
    JSON,
    Relationship,
    SQLModel,
)
from .enum import (
    DeliveryMethod,
    LengthUnit,
    PackagingType,
    SpecialHandling,
    VolumeUnit,
    WeightUnit,
)
from .company import Company
from .milestone import (
    Milestone,
    MilestoneResponse,
)

class DeliveryBase(SQLModel):
    destination: str
    method: DeliveryMethod | None = Field(default=None, sa_column=Column(Enum(DeliveryMethod)))
    schedules: list[str] | None = Field(default=None, sa_column=Column(JSON))
    width: int | None = Field(default=None)
    height: int | None = Field(default=None)
    depth: int | None = Field(default=None)
    length_unit: LengthUnit | None = Field(default=None, sa_column=Column(Enum(LengthUnit)))
    volume: int | None = Field(default=None)
    volume_unit: VolumeUnit | None = Field(default=None, sa_column=Column(Enum(VolumeUnit)))
    weight: int | None = Field(default=None)
    weight_unit: WeightUnit | None = Field(default=None, sa_column=Column(Enum(WeightUnit)))
    packaging: PackagingType | None = Field(default=None, sa_column=Column(Enum(PackagingType)))
    handling: list[SpecialHandling] | None = Field(default=None, sa_column=Column(JSON))
    value_cents: int | None = Field(default=None)
    value_currency: str | None = Field(default=None)
    extra: Any | None = Field(default=None, sa_column=Column(JSON))

class DeliveryCreate(DeliveryBase):
    milestone_id: str

class DeliveryResponse(DeliveryBase):
    id: str | int
    milestone: MilestoneResponse | None

    @field_serializer('id', when_used='json')
    def serialize_id_to_str(self, id: int):
        return str(id)

class Delivery(DeliveryBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    company_id: int = Field(foreign_key="company.id")
    milestone_id: int = Field(foreign_key="milestone.id")

    milestone: Milestone | None = Relationship()

    @model_serializer(mode='wrap')
    def serialize_model(self, handler: sfWrapHandler) -> dict[str, object]:
        # Output from default serializer
        serialized = handler(self)
        # Build 'milestone' attribute from relation
        if self.milestone:
            serialized['milestone'] = self.milestone.model_dump()
        return serialized
