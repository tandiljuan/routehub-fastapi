from pydantic import BaseModel
from .draft_route import DraftRoute

class DraftRouting(BaseModel):
    api_type: str = "igraph"
    rectify_final_routes: bool = True
    two_opt_fast_mode: bool = True

class DraftSet(BaseModel):
    origin_lat: float
    origin_lng: float
    tag: str
    zone: str = "MULTI"
    optimization_params: DraftRouting
    wait_for_response: bool = False
    routes: list[DraftRoute]
