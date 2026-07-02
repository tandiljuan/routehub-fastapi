"""Postgres row-level security (defense-in-depth).

Every tenant table is scoped to the request's company via the
``app.current_company`` GUC. Even a query that forgets ``WHERE company_id = ?``
then returns only the current company's rows (or none if the GUC is unset —
fail closed).

No-op on non-Postgres engines (e.g. SQLite in tests), where the
application-level ``company_id`` filters remain the enforcement.
"""

from contextvars import ContextVar

from sqlalchemy import event
from sqlmodel import Session as SQLModel_Session

RLS_SETTING = "app.current_company"

# Per-request company. Async tasks / threadpool workers each get their own copy.
_current_company: ContextVar[int | None] = ContextVar("current_company", default=None)


def set_current_company(company_id: int | None) -> None:
    _current_company.set(company_id)


def clear_current_company() -> None:
    _current_company.set(None)


def _set_guc(connection, company_id: int) -> None:
    # Transaction-local (is_local=true): auto-clears at commit/rollback so the
    # value can never bleed into the next user of a pooled connection.
    connection.exec_driver_sql(
        "SELECT set_config(%s, %s, true)", (RLS_SETTING, str(company_id))
    )


def apply_company_to_session(session: SQLModel_Session, company_id: int) -> None:
    """Set the RLS GUC on the session's *current* transaction.

    Called right after the API key resolves the company, so the in-flight
    transaction (which already read api_key) is scoped for the rest of the request.
    Guards on the session's own bind, so it works even if the global engine differs.
    """
    bind = session.get_bind()
    if bind.dialect.name != "postgresql":
        return
    _set_guc(session.connection(), company_id)


@event.listens_for(SQLModel_Session, "after_begin")
def _reapply_on_new_transaction(session, transaction, connection) -> None:
    # set_config(..., true) dies with its transaction; a route that commits and
    # then queries again starts a fresh transaction that must re-apply the GUC.
    if connection.dialect.name != "postgresql":
        return
    company_id = _current_company.get()
    if company_id is not None:
        _set_guc(connection, company_id)
