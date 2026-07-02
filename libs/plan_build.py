from __future__ import annotations

import math
from typing import Any

from libs.lot_plan_adapter import (
    build_plan_clustering,
    build_plan_rebalance,
    build_plan_routing,
    build_plan_settings,
    build_plan_vehicles,
)
from libs.plan_engine_defaults import resolve_engine_config
from libs.optimizer.models.plan_context import PlanContext
from libs.package_wire import build_plan_address, parse_lat_lng_from_destination
from models.lot_config import FleetRunProfile, LotConfig, config_to_lot_config

def lot_delivery_count(lot: dict[str, Any], *, fallback: int) -> int:
    if lot.get("delivery_count") is not None:
        return int(lot["delivery_count"])
    deliveries = lot.get("deliveries") or []
    if deliveries:
        return len(deliveries)
    return fallback

def compute_fallback_stops(a_sum: int, v_sum: int, lot_db) -> tuple[int, int]:
    limit_stop_min = math.ceil(a_sum * 0.95)
    limit_stop_max = math.floor(a_sum * 1.05)
    route_stops_min = math.floor(limit_stop_min / v_sum)
    route_stops_min = lot_db.route_stops_min if lot_db.route_stops_min else route_stops_min
    route_stops_max = math.ceil(limit_stop_max / v_sum)
    route_stops_max = lot_db.route_stops_max if lot_db.route_stops_max else route_stops_max
    return route_stops_min, route_stops_max

def build_plan_context_for_lot(
    *,
    lot_db,
    lot_config: LotConfig,
    fleet_links,
    delivery_rows: list[tuple[int, str, dict | None]],
    fallback_stops_min: int,
    fallback_stops_max: int,
    delivery_count: int | None = None,
) -> PlanContext:
    vehicles = build_plan_vehicles(
        fleet_links,
        lot_db,
        lot_config,
        fallback_stops_min=fallback_stops_min,
        fallback_stops_max=fallback_stops_max,
    )
    addresses = [
        build_plan_address(destination, extra, delivery_id=int(dlv_id))
        for dlv_id, destination, extra in delivery_rows
    ]
    a_sum = delivery_count if delivery_count is not None else len(delivery_rows)
    v_sum = sum(link.quantity for link in fleet_links)
    engine = resolve_engine_config()
    clustering_dict = dict(engine["clustering"])
    if (
        lot_config.clustering is not None
        and lot_config.clustering.force_vehicles_fleet_match is not None
    ):
        clustering_dict["force_vehicles_fleet_match"] = (
            lot_config.clustering.force_vehicles_fleet_match
        )
    clustering = build_plan_clustering(
        engine_clustering=clustering_dict,
        a_sum=a_sum,
        v_sum=v_sum,
    )
    routing = build_plan_routing(lot_config, engine_routing=engine["routing"])
    settings = build_plan_settings(
        engine_settings=engine["settings"],
        max_size_cluster=clustering.max_size_cluster,
    )
    rebalance = build_plan_rebalance(lot_config, lot_db)

    origin_lat, origin_lng = parse_lat_lng_from_destination(lot_db.milestone.location)

    return PlanContext(
        date=lot_config.plan_date(),
        origin_lat=origin_lat,
        origin_lng=origin_lng,
        zone=lot_config.zone or "MULTI",
        tag=lot_db.milestone.name.strip().replace(" ", "_").upper(),
        vehicles=vehicles,
        addresses=addresses,
        clustering=clustering,
        routing=routing,
        rebalance=rebalance,
        settings=settings,
    )

def fleet_links_from_api_vehicles(vehicles: list[dict[str, Any]]) -> list:
    from types import SimpleNamespace

    from models.enum import (
        VehicleConsumptionUnit,
        VehicleEngineType,
        VolumeUnit,
        WeightUnit,
    )

    links = []
    for v in vehicles:
        profile = None
        if v.get("route") or v.get("behavior"):
            profile = FleetRunProfile.model_validate(
                {k: v[k] for k in ("route", "behavior") if v.get(k)}
            )
        vol_unit = VolumeUnit(v["volume_unit"]) if v.get("volume_unit") else None
        wgt_unit = WeightUnit(v["weight_unit"]) if v.get("weight_unit") else None
        cons_unit = (
            VehicleConsumptionUnit(v["consumption_unit"]) if v.get("consumption_unit") else None
        )
        eng = VehicleEngineType(v["engine_type"]) if v.get("engine_type") else None
        links.append(
            SimpleNamespace(
                quantity=v["qty"],
                vehicle=SimpleNamespace(
                    id=int(v["id"]),
                    name=v.get("name"),
                    volume=v.get("volume"),
                    volume_unit=vol_unit,
                    weight=v.get("weight"),
                    weight_unit=wgt_unit,
                    consumption=v.get("consumption"),
                    consumption_unit=cons_unit,
                    engine_type=eng,
                ),
                run_profile=profile,
            )
        )
    return links

def lot_db_stub_from_api(lot: dict[str, Any]):
    from types import SimpleNamespace

    from models.enum import LengthUnit, TimeUnit

    rl = lot.get("route_limits") or {}
    ms = lot.get("milestone") or {}
    return SimpleNamespace(
        route_stops_min=rl.get("stops_min"),
        route_stops_max=rl.get("stops_max"),
        route_length_min=rl.get("length_min"),
        route_length_max=rl.get("length_max"),
        route_length_unit=LengthUnit(rl["length_unit"]) if rl.get("length_unit") else None,
        route_time_min=rl.get("time_min"),
        route_time_max=rl.get("time_max"),
        route_time_unit=TimeUnit(rl["time_unit"]) if rl.get("time_unit") else None,
        milestone=SimpleNamespace(
            location=ms.get("location", ""),
            name=ms.get("name", ""),
        ),
    )

def build_plan_context_from_lot_api(
    lot: dict[str, Any],
    delivery_rows: list[tuple[int, str, dict | None]],
) -> PlanContext:
    lot_db = lot_db_stub_from_api(lot)
    lot_config = config_to_lot_config(lot.get("config")) or LotConfig()
    fleet = lot.get("fleet") or {}
    vehicles = fleet.get("vehicles") or []
    v_sum = sum(int(v.get("qty", 0)) for v in vehicles)
    a_sum = lot_delivery_count(lot, fallback=len(delivery_rows))
    fb_min, fb_max = compute_fallback_stops(a_sum, v_sum, lot_db)
    links = fleet_links_from_api_vehicles(vehicles)
    return build_plan_context_for_lot(
        lot_db=lot_db,
        lot_config=lot_config,
        fleet_links=links,
        delivery_rows=delivery_rows,
        fallback_stops_min=fb_min,
        fallback_stops_max=fb_max,
        delivery_count=a_sum,
    )