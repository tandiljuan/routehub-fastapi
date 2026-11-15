"""Minimum stops per route when none is set: a share of the maximum (DEFAULT_MIN_STOPS_SHARE), not the average."""
from types import SimpleNamespace

from libs.lot_plan_adapter import _deliveries_qty, default_min_stops
from libs.plan_build import compute_fallback_stops


def _lot(**kw):
    return SimpleNamespace(route_stops_min=kw.get("min"), route_stops_max=kw.get("max"))


def _route(stops_min=None, stops_max=None):
    return SimpleNamespace(stops_min=stops_min, stops_max=stops_max)


def test_twenty_percent_of_the_maximum_rounded_down():
    assert [default_min_stops(m) for m in (55, 50, 4, None)] == [11, 10, 0, None]


def test_a_vehicle_without_minimum_gets_a_share_of_its_own_maximum():
    q = _deliveries_qty(_route(stops_max=50), _lot(), fallback_min=43, fallback_max=50)
    assert (q.min, q.max) == (10, 50)
    q = _deliveries_qty(_route(stops_max=122), _lot(), fallback_min=43, fallback_max=50)
    assert (q.min, q.max) == (24, 122)


def test_a_minimum_that_was_set_is_kept():
    assert _deliveries_qty(_route(30, 50), _lot(), 43, 50).min == 30
    assert _deliveries_qty(_route(stops_max=50), _lot(min=15), 43, 50).min == 15


def test_the_lot_fallback_minimum_is_a_share_of_its_maximum():
    # 3,310 stops on 73 vehicles: the maximum stays from the average and the cluster tolerance, the minimum is 20 % of it
    smin, smax = compute_fallback_stops(3310, 73, _lot())
    assert smin == smax * 20 // 100 and smin < 43
    assert compute_fallback_stops(3310, 73, _lot(min=30, max=50)) == (30, 50)
