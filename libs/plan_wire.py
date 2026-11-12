from __future__ import annotations

from libs.optimizer.models.plan_context import PlanContext

def plan_to_wire_payload(plan: PlanContext) -> dict:
    payload = plan.model_dump(exclude_none=True, serialize_as_any=True)
    for addr in payload.get("addresses", []):
        for pkg in addr.get("packages", []):
            if "time_window" not in pkg:
                pkg["time_window"] = None
    return payload


def wire_request(plan: PlanContext) -> dict:
    """The wire payload as plain JSON (dates and decimals as strings): what a plan stores in ``request_data`` and
    what its hash is taken from, so a stored request and a freshly built one compare equal."""
    import json
    return json.loads(json.dumps(plan_to_wire_payload(plan), default=str))
