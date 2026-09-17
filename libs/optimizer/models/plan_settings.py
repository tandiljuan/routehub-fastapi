from pydantic import BaseModel


class Preprocessing(BaseModel):
    enable_address_preprocessing: bool | None = None
    preprocessing_batch_size: int | None = None
    max_distance_km: float | None = None


class Hardware(BaseModel):
    clustering_data_chunks: int | str | None = None
    clustering_parallel_process: int | None = None
    routing_batch_size: int | None = None
    routing_parallel_process: int | None = None
    routing_strategy: str | None = None


class PlanSettings(BaseModel):
    """Typed optimizer settings payload.

    Left unset by default: the optimizer applies its own preprocessing defaults and
    computes preprocessing_batch_size; chunks and parallelism come from its deploy env.
    Fields stay declared so PLAN_SETTINGS_JSON and PLAN_PREPROCESSING_MAX_DISTANCE_KM
    overrides still reach the wire.
    """

    preprocessing: Preprocessing = Preprocessing()
    hardware: Hardware | None = None
