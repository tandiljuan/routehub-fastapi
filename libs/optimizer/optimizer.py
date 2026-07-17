import json
import requests
from libs.plan_wire import plan_to_wire_payload
from .models import (
    DraftSet,
    PlanContext,
    ResultSet,
)


class OptimizerError(Exception):
    """Raised when the external route optimizer request fails."""

    def __init__(
        self,
        message: str,
        *,
        upstream_status: int | None = None,
        upstream_body: dict | str | None = None,
    ):
        super().__init__(message)
        self.upstream_status = upstream_status
        self.upstream_body = upstream_body


class Optimizer():

    def __init__(self, host: str, port: int, auth: str = None):
        self.host = host
        self.port = port
        self.auth = auth

    def _post_session(self, url: str, payload: dict) -> str:
        headers = {'api-key': self.auth} if self.auth else {}
        try:
            r = requests.post(url, json=payload, headers=headers)
        except requests.RequestException as exc:
            raise OptimizerError(f"Optimizer unreachable: {exc}") from exc
        return self._session_id_from_response(r)

    def _session_id_from_response(self, r: requests.Response) -> str:
        try:
            body = r.json()
        except ValueError:
            snippet = (r.text or "")[:500]
            raise OptimizerError(
                f"Optimizer returned non-JSON response (HTTP {r.status_code})",
                upstream_status=r.status_code,
                upstream_body=snippet or None,
            ) from None

        if r.ok:
            session_id = body.get("session_id")
            if session_id:
                return session_id
            raise OptimizerError(
                "Optimizer response missing session_id",
                upstream_status=r.status_code,
                upstream_body=body,
            )

        detail = body.get("detail", body)
        raise OptimizerError(
            f"Optimizer rejected request (HTTP {r.status_code}): {detail}",
            upstream_status=r.status_code,
            upstream_body=body,
        )

    def send_route_plan(self, plan: PlanContext) -> str:
        payload = plan_to_wire_payload(plan)
        url = f"{self.host}:{self.port}/route-optimizer-app/routes"
        return self._post_session(url, payload)

    def get_plan_result(self, task_id: str) -> ResultSet:
        url = f"{self.host}:{self.port}/route-optimizer-app/routes/{task_id}"
        headers = {'api-key': self.auth} if self.auth else {}
        r = requests.get(url, headers=headers)
        rbody = {"status": "processing"}
        if 200 == r.status_code:
            rbody = json.loads(r.text)
            rbody['status'] = "completed"
        result_set = ResultSet.model_validate(rbody)
        return result_set

    def send_route_draft(self, draft: DraftSet):
        payload = draft.model_dump(serialize_as_any=True)
        url = f"{self.host}:{self.port}/route-optimizer-app/routes/optimize"
        return self._post_session(url, payload)

    def get_draft_result(self, task_id: str) -> ResultSet:
        url = f"{self.host}:{self.port}/route-optimizer-app/routes/optimize/{task_id}"
        headers = {'api-key': self.auth} if self.auth else {}
        r = requests.get(url, headers=headers)
        rbody = {"status": "processing"}
        if 200 == r.status_code:
            rbody = json.loads(r.text)
            # The async optimizer marks the body itself (completed/failed). Legacy
            # versions return 200 with no status even while the worker is running —
            # only a body with routes means the draft actually finished.
            if not rbody.get('status'):
                rbody['status'] = "completed" if rbody.get('routes') else "processing"
        result_set = ResultSet.model_validate(rbody)
        return result_set

    def get_route_status(self, session_id: str) -> tuple[int, dict]:
        url = f"{self.host}:{self.port}/route-optimizer-app/routes/{session_id}/status"
        headers = {'api-key': self.auth} if self.auth else {}
        r = requests.get(url, headers=headers, timeout=30)
        try:
            body = r.json()
        except ValueError:
            body = {"detail": r.text or "Optimizer error"}
        return r.status_code, body
