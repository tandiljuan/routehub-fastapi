from typing import Literal

from pydantic import BaseModel


class RouteStatusStep(BaseModel):
    id: str
    label: str
    state: Literal["pending", "active", "done"]


class RouteStatusClusteringDetails(BaseModel):
    completed_chunks: int | None = None
    total_chunks: int | None = None


class RouteStatusGraphsDetails(BaseModel):
    active_downloads: int | None = None
    completed_downloads: int | None = None
    disk_loads: int | None = None
    redis_hits: int | None = None


class RouteStatusRoutingDetails(BaseModel):
    completed_routes: int | None = None
    total_routes: int | None = None


class RouteStatusDetails(BaseModel):
    clustering: RouteStatusClusteringDetails | None = None
    graphs: RouteStatusGraphsDetails | None = None
    routing: RouteStatusRoutingDetails | None = None


class RouteStatus(BaseModel):
    session_id: str
    status: str
    phase: str | None = None
    phase_label: str | None = None
    progress_pct: int | None = None
    elapsed_seconds: int | None = None
    message: str | None = None
    details: RouteStatusDetails | None = None
    steps: list[RouteStatusStep] | None = None
