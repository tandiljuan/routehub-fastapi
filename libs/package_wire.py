from __future__ import annotations

import re
from typing import Any

from libs.optimizer.models.plan_address import PlanAddress
from libs.optimizer.models.plan_package import PlanPackage

_GEO_RGX = re.compile(r"([+-]?[\d\.]+)")

def parse_lat_lng_from_destination(destination: str) -> tuple[float, float]:
    geo = _GEO_RGX.findall(destination)
    return float(geo[0]), float(geo[1])

def address_extra_from_source(addr: dict) -> dict:
    extra: dict = {
        "lat": addr["lat"],
        "lng": addr["lng"],
    }
    if addr.get("zone") is not None:
        extra["zone"] = addr["zone"]
    if addr.get("packages"):
        extra["packages"] = addr["packages"]
    return extra

def plan_packages_from_extra(extra: Any, *, fallback_package_id: str) -> list[PlanPackage]:
    if isinstance(extra, dict):
        raw = extra.get("packages")
        if raw:
            out: list[PlanPackage] = []
            for item in raw:
                if not isinstance(item, dict) or not item.get("package_id"):
                    continue
                out.append(PlanPackage.model_validate(item))
            if out:
                return out
    return [PlanPackage(package_id=fallback_package_id)]

def wire_address_from_source(addr: dict) -> PlanAddress:
    """Build optimizer address wire from source JSON (reference shape)."""
    fallback = "0"
    raw = addr.get("packages") or []
    if raw and isinstance(raw[0], dict) and raw[0].get("package_id"):
        fallback = str(raw[0]["package_id"])
    return PlanAddress(
        lat=float(addr["lat"]),
        lng=float(addr["lng"]),
        zone=addr.get("zone"),
        packages=plan_packages_from_extra(addr, fallback_package_id=fallback),
    )

def build_plan_address(
    destination: str,
    extra: Any,
    *,
    delivery_id: int,
) -> PlanAddress:
    lat: float | None = None
    lng: float | None = None
    if isinstance(extra, dict):
        if extra.get("lat") is not None and extra.get("lng") is not None:
            lat = float(extra["lat"])
            lng = float(extra["lng"])

    if lat is None or lng is None:
        lat, lng = parse_lat_lng_from_destination(destination)

    kwargs: dict = {
        "lat": lat,
        "lng": lng,
        "packages": plan_packages_from_extra(extra, fallback_package_id=str(delivery_id)),
    }
    if isinstance(extra, dict) and extra.get("zone") is not None:
        kwargs["zone"] = extra["zone"]
    return PlanAddress(**kwargs)

def build_package_id_to_delivery_id_map(rows: list[tuple[int, str, Any]]) -> dict[str, int]:
    mapping: dict[str, int] = {}
    for dlv_id, _, extra in rows:
        dlv_id = int(dlv_id)
        mapping[str(dlv_id)] = dlv_id
        if isinstance(extra, dict):
            for pkg in extra.get("packages") or []:
                if isinstance(pkg, dict) and pkg.get("package_id"):
                    mapping[str(pkg["package_id"])] = dlv_id
    return mapping

def resolve_delivery_id(package_map: dict[str, int], package_id: str) -> int:
    pid = str(package_id)
    if pid in package_map:
        return package_map[pid]
    if pid.isdigit():
        return int(pid)
    raise ValueError(f"Unknown package_id for delivery lookup: {package_id!r}")
