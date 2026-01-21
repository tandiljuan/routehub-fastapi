from pydantic import BaseModel

class Preprocessing(BaseModel):
    enable_address_preprocessing: bool = True
    preprocessing_batch_size: int = 150 # 3 * max_size_cluster
    max_distance_km: float = 200.0

class Hardware(BaseModel):
    clustering_data_chunks: int | str = "auto"
    clustering_parallel_process: int = 8
    routing_batch_size: int = 6
    routing_parallel_process: int = 1
    routing_strategy: str = "GRANULAR_ROUTING"

class PlanSettings(BaseModel):
    generate_maps: bool = False
    preprocessing: Preprocessing = Preprocessing()
    hardware: Hardware = Hardware()
