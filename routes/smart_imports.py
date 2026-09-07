"""Authenticated proxy to vepathos-smart-import.

With SMART_IMPORT_ENABLED=false (default) these routes return 404 and the
legacy upload path is unchanged. With true, RouteHub authenticates (API key
→ company) and forwards multipart/JSON to the private smart-import service.
Browsers never talk to smart-import directly in production.
"""
from __future__ import annotations

import logging
import os
from datetime import date
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, Body, File, HTTPException, Query, UploadFile
from fastapi.responses import Response

from libs.tenant.context import CompanyDep, assert_company_match
from models.database import Session as DbSession
from models.smart_import_job import SmartImportJob

logger = logging.getLogger(__name__)

SMART_IMPORT_ENABLED = os.environ.get("SMART_IMPORT_ENABLED", "false").strip().lower() in {
    "1", "true", "yes", "on",
}
SMART_IMPORT_URL = os.environ.get("SMART_IMPORT_URL", "http://localhost:8100").rstrip("/")
SMART_IMPORT_TIMEOUT = float(os.environ.get("SMART_IMPORT_TIMEOUT", "180"))

# Same suffixes smart-import accepts. Reject here to avoid shipping a whole
# unsupported file upstream.
ALLOWED_SUFFIXES = {".csv", ".tsv", ".txt", ".xlsx", ".xlsm", ".xls", ".json"}
# Perimeter upload cap. Smart-import still enforces its own streaming limit.
MAX_UPLOAD_MB = float(os.environ.get("SMART_IMPORT_MAX_FILE_MB", "10"))

router = APIRouter(
    prefix="/imports/smart",
    tags=["smart-import"],
)


def _require_enabled() -> None:
    if not SMART_IMPORT_ENABLED:
        raise HTTPException(
            status_code=404,
            detail="Smart Import is disabled. Set SMART_IMPORT_ENABLED=true on RouteHub.",
        )


def _upstream(path: str) -> str:
    return f"{SMART_IMPORT_URL}{path}"


def _set_params(params: dict[str, Any], **values: Any) -> None:
    """Add query params only when present. None and blank strings are omitted."""
    for key, value in values.items():
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        params[key] = value


def _reject_unsupported(filename: str | None) -> None:
    suffix = Path(filename or "").suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(
            status_code=415,
            detail=(
                f"Unsupported extension {suffix or '(none)'!r}. "
                f"Allowed: {sorted(ALLOWED_SUFFIXES)}"
            ),
        )


def _reject_too_large(file: UploadFile) -> None:
    """Reject oversized uploads before forwarding.

    Starlette sets ``UploadFile.size`` after the multipart body is received.
    If size is unknown, smart-import still enforces its streaming limit.
    """
    size = getattr(file, "size", None)
    if size is not None and size > MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds {MAX_UPLOAD_MB} MB",
        )


def _rewrite_links(body: Any) -> Any:
    """Rewrite smart-import paths onto this proxy prefix.

    Upstream returns ``next_actions[].href`` and ``urls{}`` as ``/imports/...``.
    Following those would skip RouteHub auth (or hit a host the client cannot
    reach). Rewrite to ``/imports/smart/...`` so clients stay on the perimeter.
    """
    if not isinstance(body, dict):
        return body
    prefix = router.prefix  # /imports/smart

    def translate(href: Any) -> Any:
        if isinstance(href, str) and href.startswith("/imports/"):
            return prefix + href[len("/imports"):]
        return href

    if isinstance(body.get("urls"), dict):
        body["urls"] = {k: translate(v) for k, v in body["urls"].items()}
    if isinstance(body.get("next_actions"), list):
        for action in body["next_actions"]:
            if isinstance(action, dict) and "href" in action:
                action["href"] = translate(action["href"])
    return body


def _authorize_job(db: DbSession, job_id: str, company_id: int) -> SmartImportJob:
    """Resolve a job id within the caller's workspace, or 404.

    Smart Import is workspace-blind: it will serve, download or re-geocode any
    id it is handed. This is the only thing standing between one workspace and
    another's customer addresses. A foreign id returns 404, not 403 — the same
    answer as an id that never existed, so the response leaks nothing.
    """
    row = db.get(SmartImportJob, job_id)
    assert_company_match(row, company_id, "Smart Import job")
    return row


def _remember_job(db: DbSession, body: Any, company_id: int, filename: str | None) -> None:
    """Record the workspace that owns a freshly created job.

    A failure here must not sink an import that already succeeded upstream, but
    it does mean nobody can reach that job afterwards — so it is logged loudly
    rather than swallowed.
    """
    job_id = body.get("job_id") if isinstance(body, dict) else None
    if not job_id:
        logger.error("smart-import returned no job_id; cannot scope it to a workspace")
        return
    try:
        db.add(SmartImportJob(job_id=str(job_id), company_id=company_id,
                              filename=(filename or None)))
        db.commit()
    except Exception:
        db.rollback()
        logger.exception(
            "could not record smart-import job %s for company %s; "
            "the import succeeded but will not be reachable",
            job_id, company_id,
        )


def _raise_upstream_error(res: httpx.Response) -> None:
    detail: Any
    try:
        body = res.json()
        detail = body.get("detail") or body.get("error") or body
    except Exception:
        detail = res.text or f"smart-import upstream {res.status_code}"
    raise HTTPException(status_code=res.status_code, detail=detail)


@router.get("/health", summary="Smart Import upstream health (proxied)")
def smart_import_health():
    _require_enabled()
    try:
        with httpx.Client(timeout=5.0) as client:
            res = client.get(_upstream("/health"))
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"smart-import unreachable at {SMART_IMPORT_URL}: {exc}",
        ) from exc
    if res.status_code >= 400:
        _raise_upstream_error(res)
    return res.json()


@router.get("/coverage", summary="OSM PBF coverage at a point")
def smart_import_coverage(lat: float = Query(...), lon: float = Query(...)):
    """Declared before ``/{job_id}`` so ``coverage`` is not parsed as an id."""
    _require_enabled()
    try:
        with httpx.Client(timeout=10.0) as client:
            res = client.get(
                _upstream("/geocoding/coverage"),
                params={"lat": lat, "lon": lon},
            )
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"smart-import unreachable: {exc}",
        ) from exc
    if res.status_code >= 400:
        _raise_upstream_error(res)
    return res.json()


@router.post("", summary="Upload + normalize via Smart Import", status_code=201)
async def smart_import_create(
    db: DbSession,
    company_id: CompanyDep,
    file: UploadFile = File(...),
    schema: str = Query("vepathos_flat_v1"),
    phone_region: str | None = Query(None),
    timezone: str | None = Query(
        None, description="IANA TZ for the user. Time windows are interpreted here.",
    ),
    depot_timezone: str | None = Query(None, description="IANA TZ for the depot (fallback)."),
    service_date: date | None = Query(
        None, description="Service day for time windows (default: tomorrow).",
    ),
    depot_city: str | None = Query(None),
    depot_region: str | None = Query(None),
    depot_country: str | None = Query(
        None, description="Overrides phone_region for address country inference.",
    ),
    diagnostics: bool = Query(False),
):
    """Multipart proxy → POST /imports on smart-import. Auth already applied.

    Forwards every query param smart-import accepts. Without timezone / depot
    context, windows use the upstream server default and address country is
    inferred from the phone region alone.
    """
    _require_enabled()
    _reject_unsupported(file.filename)
    _reject_too_large(file)

    params: dict[str, Any] = {"schema": schema, "diagnostics": str(diagnostics).lower()}
    _set_params(
        params,
        phone_region=phone_region,
        timezone=timezone,
        depot_timezone=depot_timezone,
        depot_city=depot_city,
        depot_region=depot_region,
        depot_country=depot_country,
    )
    if service_date is not None:
        params["service_date"] = service_date.isoformat()

    # Pass the file object (not bytes) so httpx streams chunks and the proxy
    # never materializes the whole upload in memory.
    files = {
        "file": (
            file.filename or "upload.bin",
            file.file,
            file.content_type or "application/octet-stream",
        )
    }
    try:
        async with httpx.AsyncClient(timeout=SMART_IMPORT_TIMEOUT) as client:
            res = await client.post(_upstream("/imports"), params=params, files=files)
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"smart-import unreachable: {exc}",
        ) from exc
    finally:
        await file.close()
    if res.status_code >= 400:
        _raise_upstream_error(res)
    body = res.json()
    _remember_job(db, body, company_id, file.filename)
    return _rewrite_links(body)


@router.get("/{job_id}", summary="Get Smart Import job")
def smart_import_get(job_id: str, db: DbSession, company_id: CompanyDep):
    _require_enabled()
    _authorize_job(db, job_id, company_id)
    try:
        with httpx.Client(timeout=SMART_IMPORT_TIMEOUT) as client:
            res = client.get(_upstream(f"/imports/{job_id}"))
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"smart-import unreachable: {exc}",
        ) from exc
    if res.status_code >= 400:
        _raise_upstream_error(res)
    return _rewrite_links(res.json())


@router.put("/{job_id}/mapping", summary="Confirm column mapping and re-normalize")
def smart_import_mapping(
    job_id: str,
    db: DbSession,
    company_id: CompanyDep,
    mapping: dict[str, str | None] = Body(..., examples=[{"Dest.": "address", "Obs": None}]),
    phone_region: str | None = Query(None),
    timezone: str | None = Query(None),
    depot_timezone: str | None = Query(None),
    service_date: date | None = Query(None),
    depot_city: str | None = Query(None),
    depot_region: str | None = Query(None),
    depot_country: str | None = Query(None),
    diagnostics: bool = Query(False),
):
    """Apply a corrected mapping and re-normalize.

    Without this route a job stuck in ``needs_mapping_review`` had no product
    path out, even though upstream advertises ``confirm_mapping`` in
    ``next_actions``.
    """
    _require_enabled()
    _authorize_job(db, job_id, company_id)
    params: dict[str, Any] = {"diagnostics": str(diagnostics).lower()}
    _set_params(
        params,
        phone_region=phone_region,
        timezone=timezone,
        depot_timezone=depot_timezone,
        depot_city=depot_city,
        depot_region=depot_region,
        depot_country=depot_country,
    )
    if service_date is not None:
        params["service_date"] = service_date.isoformat()
    try:
        with httpx.Client(timeout=SMART_IMPORT_TIMEOUT) as client:
            res = client.put(
                _upstream(f"/imports/{job_id}/mapping"),
                params=params,
                json=mapping,
            )
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"smart-import unreachable: {exc}",
        ) from exc
    if res.status_code >= 400:
        _raise_upstream_error(res)
    return _rewrite_links(res.json())


@router.get("/{job_id}/preview", summary="Preview the resulting rows")
def smart_import_preview(
    job_id: str,
    db: DbSession,
    company_id: CompanyDep,
    limit: int = Query(20, le=200),
    source: str = Query("auto", pattern="^(auto|normalized|geocoded)$"),
):
    """Sample rows for the UI table without downloading the full CSV.

    ``auto`` returns the current result (geocoded when available).
    """
    _require_enabled()
    _authorize_job(db, job_id, company_id)
    try:
        with httpx.Client(timeout=SMART_IMPORT_TIMEOUT) as client:
            res = client.get(
                _upstream(f"/imports/{job_id}/preview"),
                params={"limit": limit, "source": source},
            )
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"smart-import unreachable: {exc}",
        ) from exc
    if res.status_code >= 400:
        _raise_upstream_error(res)
    return res.json()


@router.delete("/{job_id}", summary="Delete a Smart Import job", status_code=204)
def smart_import_delete(job_id: str, db: DbSession, company_id: CompanyDep):
    """Delete the job and its artifacts."""
    _require_enabled()
    row = _authorize_job(db, job_id, company_id)
    try:
        with httpx.Client(timeout=SMART_IMPORT_TIMEOUT) as client:
            res = client.delete(_upstream(f"/imports/{job_id}"))
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"smart-import unreachable: {exc}",
        ) from exc
    if res.status_code >= 400:
        _raise_upstream_error(res)
    # Drop the ownership row only once upstream confirmed: if this failed first,
    # the job would survive with nobody able to reach it.
    db.delete(row)
    db.commit()
    return Response(status_code=204)


@router.get("/{job_id}/progress", summary="Poll Smart Import job progress")
def smart_import_progress(job_id: str, db: DbSession, company_id: CompanyDep):
    _require_enabled()
    _authorize_job(db, job_id, company_id)
    try:
        with httpx.Client(timeout=15.0) as client:
            res = client.get(_upstream(f"/imports/{job_id}/progress"))
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"smart-import unreachable: {exc}",
        ) from exc
    if res.status_code >= 400:
        _raise_upstream_error(res)
    return res.json()


@router.get("/{job_id}/issues", summary="Row-level issues for a job")
def smart_import_issues(job_id: str, db: DbSession, company_id: CompanyDep):
    _require_enabled()
    _authorize_job(db, job_id, company_id)
    try:
        with httpx.Client(timeout=15.0) as client:
            res = client.get(_upstream(f"/imports/{job_id}/issues"))
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"smart-import unreachable: {exc}",
        ) from exc
    if res.status_code >= 400:
        _raise_upstream_error(res)
    return res.json()


@router.get("/{job_id}/download", summary="Download flat/nested/geocoded artifact")
def smart_import_download(
    job_id: str,
    db: DbSession,
    company_id: CompanyDep,
    format: str = Query("flat", pattern="^(flat|nested|geocoded|normalized)$"),
):
    _require_enabled()
    _authorize_job(db, job_id, company_id)
    try:
        with httpx.Client(timeout=SMART_IMPORT_TIMEOUT) as client:
            res = client.get(
                _upstream(f"/imports/{job_id}/download"),
                params={"format": format},
            )
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"smart-import unreachable: {exc}",
        ) from exc
    if res.status_code >= 400:
        _raise_upstream_error(res)
    content_type = res.headers.get("content-type", "application/octet-stream")
    return Response(content=res.content, media_type=content_type, status_code=res.status_code)


@router.post("/{job_id}/geocode", summary="Trigger geocode (explicit)", status_code=202)
def smart_import_geocode(
    job_id: str,
    db: DbSession,
    company_id: CompanyDep,
    origin_lat: float | None = Query(None),
    origin_lon: float | None = Query(None),
    bbox: str | None = Query(None),
    index: str | None = Query(None),
    depot_city: str | None = Query(None, description="Depot city / locality"),
    depot_region: str | None = Query(None, description="Depot province / state"),
    depot_postcode: str | None = Query(None),
    depot_country: str | None = Query(None),
    depot_address: str | None = Query(None, description="Free-form depot address"),
    max_distance_km: float | None = Query(
        None, description="Hard geofence radius in km around the depot",
    ),
    enhance_addresses: bool | None = Query(
        None,
        description=(
            "Opt-in: rewrite only the internal geocode QUERY. "
            "The user-visible address is unchanged."
        ),
    ),
):
    """Trigger geocode. Explicit user action — never automatic.

    ``depot_*`` tokens are appended to the internal query. Dropping them
    (as an earlier proxy did) left bare street names unresolved.
    """
    _require_enabled()
    _authorize_job(db, job_id, company_id)
    params: dict[str, Any] = {}
    _set_params(
        params,
        origin_lat=origin_lat,
        origin_lon=origin_lon,
        bbox=bbox,
        index=index,
        depot_city=depot_city,
        depot_region=depot_region,
        depot_postcode=depot_postcode,
        depot_country=depot_country,
        depot_address=depot_address,
        max_distance_km=max_distance_km,
    )
    if enhance_addresses is not None:
        params["enhance_addresses"] = str(enhance_addresses).lower()
    try:
        with httpx.Client(timeout=30.0) as client:
            res = client.post(_upstream(f"/imports/{job_id}/geocode"), params=params)
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"smart-import unreachable: {exc}",
        ) from exc
    if res.status_code >= 400:
        _raise_upstream_error(res)
    return _rewrite_links(res.json())
