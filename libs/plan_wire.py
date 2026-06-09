from __future__ import annotations

from libs.optimizer.models.plan_context import PlanContext

def plan_to_wire_payload(plan: PlanContext) -> dict:
    payload = plan.model_dump(exclude_none=True, serialize_as_any=True)
    for addr in payload.get("addresses", []):
        for pkg in addr.get("packages", []):
            if "time_window" not in pkg:
                pkg["time_window"] = None
    return payload
