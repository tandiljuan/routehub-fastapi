"""Distance card 1/51 must reach PlanRebalance, without inventing 20/100."""

from types import SimpleNamespace

from libs.lot_plan_adapter import build_plan_rebalance
from models.enum import LengthUnit, TimeUnit
from models.lot_config import (
    LotConfig,
    RebalanceByDistanceConfig,
    RebalanceConfig,
    VehicleRouteConfig,
    VehicleRunConfig,
    VehiclesConfig,
)


def _lot_db(*, route_length_min=None, route_length_max=None, route_length_unit=LengthUnit.KILOMETER):
    return SimpleNamespace(
        route_time_min=None,
        route_time_max=None,
        route_time_unit=TimeUnit.MINUTE,
        route_length_min=route_length_min,
        route_length_max=route_length_max,
        route_length_unit=route_length_unit,
    )


def _fleet_defaults(distance_min=1, distance_max=1250) -> VehiclesConfig:
    return VehiclesConfig(
        defaults=VehicleRunConfig(
            route=VehicleRouteConfig(
                distance_min=distance_min,
                distance_max=distance_max,
                distance_unit=LengthUnit.KILOMETER,
            )
        )
    )


def test_lot_length_one_fifty_one_beats_fleet_and_stale_branch():
    lot_config = LotConfig(
        rebalance=RebalanceConfig(
            rebalance_by_distance=RebalanceByDistanceConfig(
                enabled=True,
                min_distance_km_per_route=20,
                max_distance_km_per_route=100,
            )
        ),
        vehicles=_fleet_defaults(),
    )
    rebalance = build_plan_rebalance(
        lot_config,
        _lot_db(route_length_min=1, route_length_max=51),
    )
    assert rebalance.rebalance_by_distance is True
    assert rebalance.min_distance_km_per_route == 1
    assert rebalance.max_distance_km_per_route == 51


def test_distance_branch_beats_fleet_when_lot_has_no_length():
    lot_config = LotConfig(
        rebalance=RebalanceConfig(
            rebalance_by_distance=RebalanceByDistanceConfig(
                enabled=True,
                min_distance_km_per_route=10,
                max_distance_km_per_route=80,
            )
        ),
        vehicles=_fleet_defaults(),
    )
    rebalance = build_plan_rebalance(lot_config, _lot_db())
    assert rebalance.min_distance_km_per_route == 10
    assert rebalance.max_distance_km_per_route == 80


def test_flag_only_distance_does_not_invent_20_100():
    lot_config = LotConfig(
        rebalance=RebalanceConfig(
            rebalance_by_distance=RebalanceByDistanceConfig(enabled=True)
        )
    )
    rebalance = build_plan_rebalance(lot_config, _lot_db())
    assert rebalance.rebalance_by_distance is True
    assert rebalance.min_distance_km_per_route is None
    assert rebalance.max_distance_km_per_route is None


def test_meter_lot_length_converts_to_km_on_rebalance():
    lot_config = LotConfig(
        rebalance=RebalanceConfig(
            rebalance_by_distance=RebalanceByDistanceConfig(enabled=True)
        )
    )
    rebalance = build_plan_rebalance(
        lot_config,
        _lot_db(route_length_min=1000, route_length_max=51000, route_length_unit=LengthUnit.METER),
    )
    assert rebalance.min_distance_km_per_route == 1
    assert rebalance.max_distance_km_per_route == 51


def test_fleet_distance_fills_when_lot_and_branch_omit_km():
    lot_config = LotConfig(
        rebalance=RebalanceConfig(
            rebalance_by_distance=RebalanceByDistanceConfig(enabled=True)
        ),
        vehicles=_fleet_defaults(distance_min=1, distance_max=51),
    )
    rebalance = build_plan_rebalance(lot_config, _lot_db())
    assert rebalance.min_distance_km_per_route == 1
    assert rebalance.max_distance_km_per_route == 51
