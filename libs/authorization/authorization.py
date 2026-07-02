import hashlib
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlmodel import select

from libs.rls import apply_company_to_session, set_current_company
from models.api_key import ApiKey
from models.database import Session as DbSession

# API key convention: rh_<env>_<random>. The prefix makes keys identifiable in
# logs and to secret scanners, and separates environments.
API_KEY_PREFIX = "rh_live_"

# auto_error=False so a missing credential is a 401 (not HTTPBearer's default 403).
bearer_scheme = HTTPBearer(auto_error=False)


def hash_api_key(raw: str) -> str:
    """SHA-256 of the full key. Keys are high-entropy random, so a fast hash with
    a constant-time DB lookup is sufficient (no per-key salt needed)."""
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def authorization(
    db: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> int:
    """Authenticate the API key and resolve its workspace (company) in one step.

    Used both as the app-wide guard and as ``CompanyDep``; FastAPI caches the
    dependency per request, so the DB lookup runs once.
    """
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key",
        )
    row = db.exec(
        select(ApiKey).where(
            ApiKey.key_hash == hash_api_key(credentials.credentials),
            ApiKey.revoked_at.is_(None),
        )
    ).first()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )
    # Bind the workspace for both the app-level filters and Postgres RLS.
    set_current_company(row.company_id)
    apply_company_to_session(db, row.company_id)
    return row.company_id
