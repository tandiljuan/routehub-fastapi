from __future__ import annotations

from typing import Annotated, Any

from pydantic import BeforeValidator


def coerce_optimizer_time_window(value: Any) -> dict | None:
    """Optimizer may return time windows as [start_min, end_min] or as a dict."""
    if value is None:
        return None
    if isinstance(value, dict):
        return value
    if isinstance(value, (list, tuple)) and len(value) >= 2:
        return {"start_minutes": value[0], "end_minutes": value[1]}
    return None


OptimizerTimeWindow = Annotated[dict | None, BeforeValidator(coerce_optimizer_time_window)]
