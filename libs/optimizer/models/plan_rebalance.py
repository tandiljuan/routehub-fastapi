from pydantic import BaseModel

class PlanRebalance(BaseModel):
    rebalance_by_volume: bool = False
    rebalance_by_size: bool = True
    rebalance_by_weight: bool = False
    rebalance_by_distance: bool = False
    rebalance_by_time: bool = False

    # Sin piso de llenado. Un piso > 0 aborta el rebalance en cascada del motor
    # (clustering_processing.rebalance_clusters_in_cascade_by_volume): si el volumen
    # total de los clusters no alcanza Σ(capacidad × ratio) devuelve los clusters sin
    # tocar. Con paquetes sin volumen declarado ese total es 0 y no rebalanceaba nunca.
    min_volume_capacity_ratio_vehicle_initial: float = 0.0
    max_volume_capacity_ratio_vehicle_initial: float = 0.95
    min_volume_capacity_ratio_vehicle: float = 0.0
    # 95% like every channel (engine default); a lot asks for 1.0 to fill vehicles completely.
    max_volume_capacity_ratio_vehicle: float = 0.95
    max_volume_capacity_ratio_total: float = 0.99

    # Mismo motivo: un paquete sin peso no debe impedir el rebalance.
    min_weight_capacity_ratio_vehicle: float = 0.0
    max_weight_capacity_ratio_vehicle: float = 0.95

    min_time_minutes_per_route: float = 60.0
    max_time_minutes_per_route: float = 420.0
    # Optional. Omit on the wire when unset (plan_to_wire exclude_none).
    min_distance_km_per_route: Optional[float] = None
    max_distance_km_per_route: Optional[float] = None

    update_volume_capacity_vehicle: bool = False
    max_neighbors_per_cluster: int = 15

    rebalance_prepass_enabled: bool = True
    rebalance_prepass_max_iters: int = 1
    rebalance_prepass_max_moves_per_region: int = 60
