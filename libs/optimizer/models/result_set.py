from pydantic import BaseModel
from .result_route import ResultRoute
from .result_total import ResultTotal

class ResultSet(BaseModel):
    session_id: str | None = None
    status: str | None = None
    routes: list[ResultRoute] | None = None
