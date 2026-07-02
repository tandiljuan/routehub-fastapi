"""Normalize optimizer time_window shapes for RouteHub JSON responses."""

from libs.optimizer.models.time_window import coerce_optimizer_time_window


def normalize_time_window(value: object) -> dict | None:
    return coerce_optimizer_time_window(value)


def normalize_waypoint_payload(item: dict) -> dict:
    """Normalize time_window on a waypoint dict and nested packages."""
    tw = normalize_time_window(item.get("time_window"))
    if tw is not None:
        item["time_window"] = tw
    elif "time_window" in item:
        item.pop("time_window", None)

    packages = item.get("packages")
    if isinstance(packages, list):
        for pkg in packages:
            if isinstance(pkg, dict):
                pkg_tw = normalize_time_window(pkg.get("time_window"))
                if pkg_tw is not None:
                    pkg["time_window"] = pkg_tw
                elif "time_window" in pkg:
                    pkg.pop("time_window", None)
    return item


def normalize_waypoints_payload(waypoints: list[dict] | None) -> list[dict]:
    if not waypoints:
        return []
    return [normalize_waypoint_payload(dict(wp)) for wp in waypoints if isinstance(wp, dict)]
