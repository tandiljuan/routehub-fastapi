"""HTTP client for vepathos-bks-optimizer, the service that improves a plan's routes (BKS search).

The service is private: RouteHub authenticates the caller (API key → company) and forwards the request with
the service key and the company id. Every call returns the service's JSON as a dict, except ``routes``,
which returns the engine-format ResultSet that ``persist_processing_plan_routes`` already stores.

Errors keep the service's body ``{"error": {"code", "message", "details"}}``: ``BksOptimizerError`` carries the
upstream HTTP status and code so the route can answer with the same meaning. A network failure or a 5xx is
``status=None`` / 5xx and maps to 502.
"""
from __future__ import annotations

from typing import Any

import httpx

from libs.optimizer.models import ResultSet

PREFIX = "/v1/bks-optimizations"


class BksOptimizerError(Exception):
    """A failed call to vepathos-bks-optimizer."""

    def __init__(self, message: str, *, status: int | None = None, code: str | None = None,
                 details: dict | None = None, retry_after: str | None = None):
        super().__init__(message)
        self.status, self.code, self.details, self.retry_after = status, code, details, retry_after


class BksOptimizer:
    def __init__(self, url: str, api_key: str, timeout: float = 30.0, transport: httpx.BaseTransport | None = None):
        self.url = url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.transport = transport  # tests inject an httpx.MockTransport

    def _call(self, method: str, path: str, company_id: int, *, json: dict | None = None,
              params: dict | None = None, idempotency_key: str | None = None) -> Any:
        headers = {"Authorization": f"Bearer {self.api_key}", "X-Vepathos-Company-Id": str(company_id)}
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        try:
            with httpx.Client(timeout=self.timeout, transport=self.transport) as client:
                r = client.request(method, f"{self.url}{path}", json=json, params=params, headers=headers)
        except httpx.HTTPError as exc:
            raise BksOptimizerError(f"BKS optimizer unreachable: {exc}") from exc
        if r.status_code >= 400:
            try:
                err = r.json().get("error") or {}
            except ValueError:
                err = {}
            raise BksOptimizerError(err.get("message") or f"BKS optimizer answered {r.status_code}",
                                    status=r.status_code, code=err.get("code"), details=err.get("details"),
                                    retry_after=r.headers.get("Retry-After"))
        return r.json()

    def capabilities(self, company_id: int) -> dict:
        return self._call("GET", f"{PREFIX}/capabilities", company_id)

    def preflight(self, company_id: int, body: dict) -> dict:
        return self._call("POST", f"{PREFIX}/preflight", company_id, json=body)

    def submit(self, company_id: int, body: dict, idempotency_key: str) -> dict:
        """Queue an optimization. The same key with the same body returns the same optimization."""
        return self._call("POST", PREFIX, company_id, json=body, idempotency_key=idempotency_key)

    def get(self, company_id: int, optimization_id: str) -> dict:
        return self._call("GET", f"{PREFIX}/{optimization_id}", company_id)

    def list(self, company_id: int, lot_id: str | None = None) -> list[dict]:
        return self._call("GET", PREFIX, company_id, params={"lot_id": lot_id} if lot_id else None)["items"]

    def cancel(self, company_id: int, optimization_id: str) -> dict:
        return self._call("POST", f"{PREFIX}/{optimization_id}/cancel", company_id)

    def solutions(self, company_id: int, optimization_id: str, params: dict | None = None) -> dict:
        return self._call("GET", f"{PREFIX}/{optimization_id}/solutions", company_id, params=params)

    def solution(self, company_id: int, optimization_id: str, solution_id: str) -> dict:
        return self._call("GET", f"{PREFIX}/{optimization_id}/solutions/{solution_id}", company_id)

    def routes(self, company_id: int, optimization_id: str, solution_id: str) -> ResultSet:
        body = self._call("GET", f"{PREFIX}/{optimization_id}/solutions/{solution_id}/routes", company_id)
        return ResultSet.model_validate(body)

    def select(self, company_id: int, optimization_id: str, solution_id: str) -> dict:
        """Record the picked solution: it is the one the service keeps after its retention window."""
        return self._call("POST", f"{PREFIX}/{optimization_id}/solutions/{solution_id}/select", company_id)
