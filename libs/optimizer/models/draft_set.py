from typing import Any

from pydantic import BaseModel
from .draft_route import DraftRoute

_LOT_DRAFT_ROUTING_KEYS = (
    "use_graph_travel_time",
    "avg_speed_kph",
    "service_time_min",
)


class DraftRouting(BaseModel):
    # Engine tuning unset: /routes/optimize applies the optimizer's own defaults.
    api_type: str | None = None
    rectify_final_routes: bool | None = None
    two_opt_fast_mode: bool | None = None
    use_graph_travel_time: bool | None = None
    avg_speed_kph: float | None = None
    service_time_min: float | None = None


def draft_routing_from_lot(lot_config: Any | None) -> DraftRouting:
    """Copy lot ETA knobs onto a draft. None stays unset so engine defaults apply.

    False is a real value and must be sent (exclude_none must not drop it).
    """
    kwargs: dict[str, Any] = {}
    routing = getattr(lot_config, "routing", None) if lot_config is not None else None
    if routing is not None:
        dumped = routing.model_dump(exclude_none=True)
        for key in _LOT_DRAFT_ROUTING_KEYS:
            if key in dumped:
                kwargs[key] = dumped[key]
    return DraftRouting(**kwargs)


class DraftSet(BaseModel):
    origin_lat: float
    origin_lng: float
    tag: str
    zone: str = "MULTI"
    optimization_params: DraftRouting
    wait_for_response: bool = False
    routes: list[DraftRoute]
