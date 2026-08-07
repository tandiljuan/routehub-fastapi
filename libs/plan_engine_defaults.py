from __future__ import annotations

import json
import os
from copy import deepcopy
from typing import Any

ENGINE_CONFIG_KEYS = frozenset({"clustering", "routing", "settings"})

# Clustering keys the web client may set per run (rest stay server-owned).
CLIENT_CLUSTERING_KEYS = frozenset({"force_vehicles_fleet_match"})

_DEFAULT_CLUSTERING: dict[str, Any] = {
    "size_cluster_tolerance": 0.15,
    "allow_subclustering_by_volume": True,
    "volume_divide_threshold": 1.4,
    "allow_subclustering_by_capacity": True,
    "capacity_divide_threshold": 1.5,
    "force_vehicles_fleet_match": False,
    "force_split_clusters": False,
}

_DEFAULT_ROUTING: dict[str, Any] = {
    "api_type": "igraph",
    "weight_routes": "length",
    "optimize_time_windows": True,
    "rectify_final_routes": True,
    "nearby_threshold_m": 15.0,
    "reorder_nearby_postprocessing": True,
    "reorder_nearby_max_penalty": 1.15,
    "distance_haversine_limit": 20,
    "distance_factor": 1.55,
    "start_time_minutes_route": 800,
    "service_time_min": 1.1,
    "avg_speed_kph": 40.0,
    "early_tolerance_min": 5.0,
    "late_tolerance_min": 10.0,
    "use_graph_travel_time": False,
    "two_opt_fast_mode": True,
    "two_opt_min_improvement_pct": 0.0075,
    "two_opt_base_max_iterations": 40,
    "two_opt_base_consecutive_limit": 25,
    "two_opt_base_total_limit": 25,
}

_DEFAULT_SETTINGS: dict[str, Any] = {
    "preprocessing": {
        "enable_address_preprocessing": True,
        "max_distance_km": 100.0,
    },
    "hardware": {
        "clustering_data_chunks": "auto",
        "clustering_parallel_process": 6,
        "routing_batch_size": 6,
        "routing_parallel_process": 6,
        "routing_strategy": "GRANULAR_ROUTING",
    },
}

# Tiered multipliers for dynamic fleet (force_vehicles_fleet_match=false).
DYNAMIC_FLEET_CLUSTER_BOOST_STOP_TIER_LOW = 2000
DYNAMIC_FLEET_CLUSTER_BOOST_STOP_TIER_MID = 5000
DYNAMIC_FLEET_CLUSTER_BOOST_UP_TO_2K = 1.0
DYNAMIC_FLEET_CLUSTER_BOOST_2K_TO_5K = 1.15
DYNAMIC_FLEET_CLUSTER_BOOST_ABOVE_5K = 1.25

def _deep_merge(base: dict, overlay: dict) -> dict:
    out = dict(base)
    for key, val in overlay.items():
        if val is None:
            continue
        if key in out and isinstance(out[key], dict) and isinstance(val, dict):
            out[key] = _deep_merge(out[key], val)
        else:
            out[key] = val
    return out

def _load_json_env(name: str) -> dict[str, Any] | None:
    raw = os.environ.get(name)
    if not raw:
        return None
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError(f"{name} must be a JSON object")
    return parsed

def engine_clustering_defaults() -> dict[str, Any]:
    return deepcopy(_load_json_env("PLAN_CLUSTERING_JSON") or _DEFAULT_CLUSTERING)

def engine_routing_defaults() -> dict[str, Any]:
    return deepcopy(_load_json_env("PLAN_ROUTING_JSON") or _DEFAULT_ROUTING)

def _apply_preprocessing_max_distance_env(settings: dict[str, Any]) -> dict[str, Any]:
    """Overlay PLAN_PREPROCESSING_MAX_DISTANCE_KM onto settings.preprocessing.

    Values:
      unset / empty → leave defaults (or PLAN_SETTINGS_JSON) unchanged
      number        → set preprocessing.max_distance_km to that km
      none/null/off → remove the key so the optimizer skips distance filtering
    """
    raw = os.environ.get("PLAN_PREPROCESSING_MAX_DISTANCE_KM")
    if raw is None or not str(raw).strip():
        return settings

    value = str(raw).strip().lower()
    preprocessing = dict(settings.get("preprocessing") or {})

    if value in {"none", "null", "off", "false"}:
        preprocessing.pop("max_distance_km", None)
    else:
        try:
            km = float(value)
        except ValueError as exc:
            raise ValueError(
                "PLAN_PREPROCESSING_MAX_DISTANCE_KM must be a number of km, "
                'or "none"/"off" to disable distance filtering'
            ) from exc
        if km <= 0:
            raise ValueError(
                "PLAN_PREPROCESSING_MAX_DISTANCE_KM must be > 0 "
                '(use "none" to disable distance filtering)'
            )
        preprocessing["max_distance_km"] = km

    settings["preprocessing"] = preprocessing
    return settings


def engine_settings_defaults() -> dict[str, Any]:
    settings = deepcopy(_load_json_env("PLAN_SETTINGS_JSON") or _DEFAULT_SETTINGS)
    return _apply_preprocessing_max_distance_env(settings)

def coerce_bool(value: Any) -> bool:
    """Normalize bools from JSON, env strings, or query params."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off", ""}:
            return False
    return bool(value)


def dynamic_fleet_cluster_size_boost(delivery_count: int) -> float:
    """Scale auto min/max cluster sizes by stop volume when dynamic fleet is enabled."""
    if delivery_count <= DYNAMIC_FLEET_CLUSTER_BOOST_STOP_TIER_LOW:
        return DYNAMIC_FLEET_CLUSTER_BOOST_UP_TO_2K
    if delivery_count <= DYNAMIC_FLEET_CLUSTER_BOOST_STOP_TIER_MID:
        return DYNAMIC_FLEET_CLUSTER_BOOST_2K_TO_5K
    return DYNAMIC_FLEET_CLUSTER_BOOST_ABOVE_5K

def resolve_engine_config(overlay: dict[str, Any] | None = None) -> dict[str, Any]:
    resolved = {
        "clustering": engine_clustering_defaults(),
        "routing": engine_routing_defaults(),
        "settings": engine_settings_defaults(),
    }
    if not overlay:
        return resolved
    for key in ENGINE_CONFIG_KEYS:
        val = overlay.get(key)
        if isinstance(val, dict):
            resolved[key] = _deep_merge(resolved[key], val)
    return resolved

def strip_engine_keys_from_config(config: dict[str, Any] | None) -> dict[str, Any] | None:
    if not config:
        return config
    out = dict(config)

    clustering = out.pop("clustering", None)
    preserved_clustering: dict[str, Any] = {}
    if isinstance(clustering, dict):
        for key in CLIENT_CLUSTERING_KEYS:
            if clustering.get(key) is not None:
                preserved_clustering[key] = clustering[key]
    if preserved_clustering:
        out["clustering"] = preserved_clustering

    for key in ENGINE_CONFIG_KEYS:
        if key == "clustering":
            continue
        out.pop(key, None)
    return out or None
