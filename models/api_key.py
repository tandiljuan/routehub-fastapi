from datetime import datetime, timezone

from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ApiKey(SQLModel, table=True):
    """A per-application API key. The key itself is never stored — only its
    SHA-256 hash. The row binds the key to a single workspace (company)."""

    __tablename__ = "api_key"

    id: int | None = Field(default=None, primary_key=True)
    company_id: int = Field(foreign_key="company.id")
    name: str = Field(max_length=100)
    key_prefix: str = Field(max_length=16)
    key_hash: str = Field(max_length=64, unique=True, index=True)
    created_at: datetime = Field(default_factory=_utcnow)
    last_used_at: datetime | None = None
    revoked_at: datetime | None = None
