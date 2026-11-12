from datetime import datetime, timezone

from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class BksOptimization(SQLModel, table=True):
    """Binds a vepathos-bks-optimizer optimization to the workspace and the lot that requested it.

    The service keeps the optimization (state, solution cards, routes) and is scoped only by an opaque
    company header, so this row is the authorization record: a caller can reach an optimization only
    through a lot of its own workspace. State is not copied here; it is read from the service.

    ``context_hash`` is the SHA-256 of the plan request that was sent. If building the request for the
    lot today gives another hash, the lot changed (deliveries, fleet, limits) and the optimization's
    solutions no longer apply to it.
    """

    __tablename__ = "bks_optimization"

    #: Upstream id (``bko_`` + 12 hex). Opaque here; never generated locally.
    optimization_id: str = Field(primary_key=True, max_length=32)
    company_id: int = Field(foreign_key="company.id", index=True)
    delivery_lot_id: int = Field(foreign_key="delivery_lot.id", index=True)
    base_plan_id: int | None = Field(default=None, foreign_key="delivery_plan.id")
    context_hash: str = Field(max_length=64)
    label: str | None = Field(default=None, max_length=120)
    selected_solution_id: str | None = Field(default=None, max_length=16)
    result_plan_id: int | None = Field(default=None, foreign_key="delivery_plan.id")
    created_at: datetime = Field(default_factory=_utcnow)
