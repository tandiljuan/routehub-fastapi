from datetime import datetime, timezone

from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SmartImportJob(SQLModel, table=True):
    """Binds a Smart Import job to the workspace that created it.

    Smart Import itself is workspace-blind: it keeps jobs in memory keyed by an
    opaque ``imp_<hex>`` id and will serve, download or re-geocode any id it is
    given. Without this row, an authenticated caller from workspace A could read
    workspace B's import — customer addresses and phone numbers — just by
    holding the id, which travels in URLs, logs and support tickets.

    The row is the authorization record, not a copy of the job: state, report
    and files stay upstream. Rows are disposable — Smart Import purges the job
    itself after its own TTL, so a stale row simply resolves to a 404 upstream.
    """

    __tablename__ = "smart_import_job"

    #: Upstream id (``imp_`` + 12 hex). Opaque here; never generated locally.
    job_id: str = Field(primary_key=True, max_length=64)
    company_id: int = Field(foreign_key="company.id", index=True)
    filename: str | None = Field(default=None, max_length=255)
    created_at: datetime = Field(default_factory=_utcnow)
