from pydantic import BaseModel

from libs.plan_engine_defaults import _DEFAULT_SETTINGS as _S

_P = _S["preprocessing"]
_H = _S["hardware"]


class Preprocessing(BaseModel):
    enable_address_preprocessing: bool = _P["enable_address_preprocessing"]
    preprocessing_batch_size: int | None = None
    max_distance_km: float | None = _P.get("max_distance_km")


class Hardware(BaseModel):
    clustering_data_chunks: int | str = _H["clustering_data_chunks"]
    clustering_parallel_process: int = _H["clustering_parallel_process"]
    routing_batch_size: int = _H["routing_batch_size"]
    routing_parallel_process: int = _H["routing_parallel_process"]
    routing_strategy: str = _H["routing_strategy"]


class PlanSettings(BaseModel):
    """Typed optimizer settings payload.

    Tunable defaults come from ``config/engine_defaults.json`` (settings).
    ``preprocessing_batch_size`` is computed per plan when omitted.
    """

    preprocessing: Preprocessing = Preprocessing()
    hardware: Hardware = Hardware()
