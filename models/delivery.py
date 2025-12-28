from typing import Any
from sqlmodel import (
    Column,
    Enum,
    Field,
    JSON,
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
