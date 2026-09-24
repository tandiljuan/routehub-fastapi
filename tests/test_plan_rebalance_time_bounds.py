"""Duration card 0/60 must beat fleet catalog, stale time-branch, and PlanRebalance 60/420."""

from types import SimpleNamespace

from libs.lot_plan_adapter import build_plan_rebalance
from models.enum import TimeUnit
from models.lot_config import (
    LotConfig,
    RebalanceByTimeConfig,
    RebalanceConfig,
    VehicleRouteConfig,
    VehicleRunConfig,
    VehiclesConfig,
)


def _lot_db(*, route_time_min=None, route_time_max=None, route_time_unit=TimeUnit.MINUTE):
    return SimpleNamespace(
        route_time_min=route_time_min,
        route_time_max=route_time_max,
        route_time_unit=route_time_unit,
    )


def _fleet_defaults(time_min=60, time_max=90, unit=TimeUnit.MINUTE) -> VehiclesConfig:
    return VehiclesConfig(
        defaults=VehicleRunConfig(
            route=VehicleRouteConfig(
                time_min=time_min,
                time_max=time_max,
                time_unit=unit,
            )
        )
    )


def test_lot_route_limits_zero_sixty_beat_fleet_defaults():
    lot_config = LotConfig(vehicles=_fleet_defaults())
    rebalance = build_plan_rebalance(
        lot_config,
        _lot_db(route_time_min=0, route_time_max=60),
    )
    assert rebalance.min_time_minutes_per_route == 0
    assert rebalance.max_time_minutes_per_route == 60


def test_lot_route_limits_beat_stale_time_branch_and_fleet():
    """UI 0/60 on the lot must not be replaced by branch 360 or fleet 6h."""
    lot_config = LotConfig(
        rebalance=RebalanceConfig(
            rebalance_by_time=RebalanceByTimeConfig(
                enabled=True,
                min_time_minutes_per_route=0,
                max_time_minutes_per_route=360,
            )
        ),
        vehicles=_fleet_defaults(time_min=6, time_max=6, unit=TimeUnit.HOUR),
    )
    rebalance = build_plan_rebalance(
        lot_config,
        _lot_db(route_time_min=0, route_time_max=60),
    )
    assert rebalance.rebalance_by_time is True
    assert rebalance.min_time_minutes_per_route == 0
    assert rebalance.max_time_minutes_per_route == 60


def test_time_branch_beats_fleet_when_lot_has_no_time_bounds():
    lot_config = LotConfig(
        rebalance=RebalanceConfig(
            rebalance_by_time=RebalanceByTimeConfig(
                enabled=True,
                min_time_minutes_per_route=0,
                max_time_minutes_per_route=60,
            )
        ),
        vehicles=_fleet_defaults(),
    )
    rebalance = build_plan_rebalance(lot_config, _lot_db())
    assert rebalance.rebalance_by_time is True
    assert rebalance.min_time_minutes_per_route == 0
    assert rebalance.max_time_minutes_per_route == 60


def test_fleet_six_hours_fills_when_lot_and_branch_omit_max():
    lot_config = LotConfig(
        rebalance=RebalanceConfig(
            rebalance_by_time=RebalanceByTimeConfig(
                enabled=True,
                min_time_minutes_per_route=0,
            )
        ),
        vehicles=_fleet_defaults(time_min=1, time_max=6, unit=TimeUnit.HOUR),
    )
    rebalance = build_plan_rebalance(lot_config, _lot_db())
    assert rebalance.min_time_minutes_per_route == 0
    assert rebalance.max_time_minutes_per_route == 360


def test_fleet_defaults_fill_when_lot_has_no_time_bounds():
    lot_config = LotConfig(vehicles=_fleet_defaults())
    rebalance = build_plan_rebalance(lot_config, _lot_db())
    assert rebalance.min_time_minutes_per_route == 60
    assert rebalance.max_time_minutes_per_route == 90
