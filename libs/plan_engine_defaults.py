from __future__ import annotations

import json
import os
from copy import deepcopy
from pathlib import Path
from typing import Any

ENGINE_CONFIG_KEYS = frozenset({"clustering", "routing", "settings"})

# Clustering keys the web client may set per run (rest stay server-owned).
CLIENT_CLUSTERING_KEYS = frozenset({"force_vehicles_fleet_match"})

# Routing keys the web client may override per run (ETA / timing). Engine-only
# knobs (2-opt, nearby, haversine, …) stay server-owned.
CLIENT_ROUTING_KEYS = frozenset({
    "service_time_min",
    "avg_speed_kph",
})

# Lot/schedule overlays — never stored in engine_defaults.json.
# start_time / time-window flags come from config.schedule; fleet-match from
# config.clustering; force_split_clusters is derived in build_plan_clustering.
SCHEDULE_ROUTING_KEYS = frozenset({
    "optimize_time_windows",
    "start_time_minutes_route",
    "early_tolerance_min",
    "late_tolerance_min",
})

REQUIRED_CLUSTERING_KEYS = frozenset({
    "size_cluster_tolerance",
    "allow_subclustering_by_volume",
    "volume_divide_threshold",
    "allow_subclustering_by_capacity",
    "capacity_divide_threshold",
})
REQUIRED_ROUTING_KEYS = frozenset({
    "api_type",
    "weight_routes",
    "rectify_final_routes",
    "nearby_threshold_m",
    "reorder_nearby_postprocessing",
    "reorder_nearby_max_penalty",
    "distance_haversine_limit",
    "distance_factor",
    "use_graph_travel_time",
    "two_opt_fast_mode",
    "two_opt_min_improvement_pct",
    "two_opt_base_max_iterations",
    "two_opt_base_consecutive_limit",
    "two_opt_base_total_limit",
})

_REPO_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_ENGINE_DEFAULTS_PATH = _REPO_ROOT / "config" / "engine_defaults.json"


def _engine_defaults_path() -> Path:
    raw = os.environ.get("ENGINE_DEFAULTS_PATH", "").strip()
    return Path(raw) if raw else _DEFAULT_ENGINE_DEFAULTS_PATH


def _load_engine_defaults_file() -> dict[str, Any]:
    path = _engine_defaults_path()
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise FileNotFoundError(
            f"Engine defaults file not found: {path}. "
            "Set ENGINE_DEFAULTS_PATH or add config/engine_defaults.json"
        ) from exc
    if not isinstance(loaded, dict):
        raise ValueError(f"{path} must contain a JSON object")
    for key in ENGINE_CONFIG_KEYS:
        section = loaded.get(key)
        if not isinstance(section, dict):
            raise ValueError(f"{path} must include a JSON object at '{key}'")
    missing_c = REQUIRED_CLUSTERING_KEYS - loaded["clustering"].keys()
    if missing_c:
        raise ValueError(f"{path} clustering missing keys: {sorted(missing_c)}")
    missing_r = REQUIRED_ROUTING_KEYS - loaded["routing"].keys()
    if missing_r:
        raise ValueError(f"{path} routing missing keys: {sorted(missing_r)}")
    return loaded


# Loaded from config/engine_defaults.json (or ENGINE_DEFAULTS_PATH).
# PLAN_*_JSON env vars merge on top at resolve time.
_ENGINE_DEFAULTS = _load_engine_defaults_file()
_DEFAULT_CLUSTERING: dict[str, Any] = _ENGINE_DEFAULTS["clustering"]
_DEFAULT_ROUTING: dict[str, Any] = _ENGINE_DEFAULTS["routing"]
_DEFAULT_SETTINGS: dict[str, Any] = _ENGINE_DEFAULTS["settings"]

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

def _with_json_overlay(base: dict[str, Any], env_name: str) -> dict[str, Any]:
    out = deepcopy(base)
    overlay = _load_json_env(env_name)
    if overlay:
        out = _deep_merge(out, overlay)
    return out


def engine_clustering_defaults() -> dict[str, Any]:
    return _with_json_overlay(_DEFAULT_CLUSTERING, "PLAN_CLUSTERING_JSON")

def engine_routing_defaults() -> dict[str, Any]:
    return _with_json_overlay(_DEFAULT_ROUTING, "PLAN_ROUTING_JSON")

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
    settings = _with_json_overlay(_DEFAULT_SETTINGS, "PLAN_SETTINGS_JSON")
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

    routing = out.pop("routing", None)
    preserved_routing: dict[str, Any] = {}
    if isinstance(routing, dict):
        for key in CLIENT_ROUTING_KEYS:
            if routing.get(key) is not None:
                preserved_routing[key] = routing[key]
    if preserved_routing:
        out["routing"] = preserved_routing

    for key in ENGINE_CONFIG_KEYS:
        if key in {"clustering", "routing"}:
            continue
        out.pop(key, None)
    return out or None
