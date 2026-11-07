"""Per-vehicle clock (service, speed, graph travel times) and U-turn rule reach the optimizer.

Lot config vehicles.defaults.routing / overrides[].routing override the plan's routing.* for that vehicle's routes;
allow_uturns there overrides the catalog vehicle. Nothing configured → nothing sent (the engine resolves
route > vehicle > plan > its default).
"""

from __future__ import annotations

import os
import unittest
from types import SimpleNamespace

os.environ.setdefault("RDBMS_URL", "sqlite://")

from libs.lot_plan_adapter import build_plan_vehicles, vehicle_clock
from libs.optimizer.models.draft_route import DraftRoute
from libs.optimizer.models.plan_vehicle import PlanVehicle
from models.enum import VehicleCategoryType
from models.vehicle import VehicleCreate
from models.lot_config import LotConfig, config_to_lot_config


def _link(*, name: str, vid: int, category=None, allow_uturns=None, avg_speed_kph=None, service_time_min=None) -> SimpleNamespace:
    return SimpleNamespace(
        quantity=1, alias=None,
        vehicle=SimpleNamespace(
            id=vid, name=name,
            volume=None, volume_unit=None, weight=None, weight_unit=None,
            consumption=None, consumption_unit=None, engine_type=None,
            category_type=category, allow_uturns=allow_uturns,
            avg_speed_kph=avg_speed_kph, service_time_min=service_time_min,
        ),
        run_profile=None,
    )


def _lot_stub() -> SimpleNamespace:
    return SimpleNamespace(
        route_stops_min=None, route_stops_max=None,
        route_length_min=None, route_length_max=None, route_length_unit=None,
        route_time_min=None, route_time_max=None, route_time_unit=None,
    )


_CONFIG = {
    "routing": {"service_time_min": 2.0, "avg_speed_kph": 40, "use_graph_travel_time": True},
    "vehicles": {
        "defaults": {"routing": {"service_time_min": 1.0}},
        "overrides": [{"vehicle_id": "7", "routing": {"service_time_min": 0.25, "avg_speed_kph": 9.6,
                                                      "use_graph_travel_time": False, "allow_uturns": True}}],
    },
}


class TestLotConfig(unittest.TestCase):
    def test_the_clock_survives_the_lot_whitelist(self):
        lot = config_to_lot_config(_CONFIG)
        self.assertEqual(lot.vehicles.defaults.routing.service_time_min, 1.0)
        [override] = lot.vehicles.overrides
        self.assertEqual((override.routing.avg_speed_kph, override.routing.use_graph_travel_time, override.routing.allow_uturns),
                         (9.6, False, True))

    def test_out_of_range_values_are_dropped(self):
        lot = config_to_lot_config({"vehicles": {"defaults": {"routing": {"service_time_min": -3, "avg_speed_kph": 0}}}})
        self.assertIsNone(lot.vehicles.defaults.routing.service_time_min)
        self.assertIsNone(lot.vehicles.defaults.routing.avg_speed_kph)


class TestPlanVehicles(unittest.TestCase):
    def test_override_beats_defaults_beats_nothing(self):
        lot = config_to_lot_config(_CONFIG)
        bike, van = build_plan_vehicles(
            [_link(name="Bici", vid=7, category=VehicleCategoryType.BICYCLE, allow_uturns=False),
             _link(name="Van", vid=8, category=VehicleCategoryType.VAN)],
            _lot_stub(), lot)
        bike_wire = bike.model_dump(exclude_none=True)
        self.assertEqual((bike_wire["service_time_min"], bike_wire["avg_speed_kph"], bike_wire["use_graph_travel_time"]),
                         (0.25, 9.6, False))
        self.assertIs(bike_wire["allow_uturns"], True)  # the plan's override beats the catalog's False
        van_wire = van.model_dump(exclude_none=True)
        self.assertEqual(van_wire["service_time_min"], 1.0)  # vehicles.defaults
        self.assertNotIn("avg_speed_kph", van_wire)
        self.assertNotIn("use_graph_travel_time", van_wire)
        self.assertNotIn("allow_uturns", van_wire)

    def test_the_catalog_clock_is_inherited_and_the_plan_override_beats_it(self):
        catalog = _link(name="Bici", vid=7, category=VehicleCategoryType.BICYCLE, avg_speed_kph=10.0, service_time_min=0.5)
        [bike] = build_plan_vehicles([catalog], _lot_stub(), LotConfig())
        wire = bike.model_dump(exclude_none=True)
        self.assertEqual((wire["avg_speed_kph"], wire["service_time_min"]), (10.0, 0.5))
        self.assertNotIn("use_graph_travel_time", wire)
        [bike] = build_plan_vehicles([catalog], _lot_stub(), config_to_lot_config(_CONFIG))
        wire = bike.model_dump(exclude_none=True)
        self.assertEqual((wire["avg_speed_kph"], wire["service_time_min"]), (9.6, 0.25))  # the plan's override wins
        self.assertEqual(VehicleCreate(name="x", avg_speed_kph=10, service_time_min=0.5).avg_speed_kph, 10)

    def test_without_config_the_catalog_rule_still_travels_and_nothing_else(self):
        [van] = build_plan_vehicles([_link(name="Van", vid=1, allow_uturns=False)], _lot_stub(), LotConfig())
        wire = van.model_dump(exclude_none=True)
        self.assertIs(wire["allow_uturns"], False)
        for key in ("service_time_min", "avg_speed_kph", "use_graph_travel_time"):
            self.assertNotIn(key, wire)


class TestReoptimization(unittest.TestCase):
    def test_a_draft_route_carries_its_vehicle_clock(self):
        lot = config_to_lot_config(_CONFIG)
        vehicle = SimpleNamespace(id=7, name="Bici", allow_uturns=None)
        clock = vehicle_clock(lot, vehicle)
        route = DraftRoute(route_id="1", waypoints=[], **clock)
        wire = route.model_dump(exclude_none=True)
        self.assertEqual((wire["service_time_min"], wire["avg_speed_kph"], wire["use_graph_travel_time"], wire["allow_uturns"]),
                         (0.25, 9.6, False, True))
        self.assertEqual(vehicle_clock(None, SimpleNamespace(id=9, name="X", allow_uturns=None)), {})

    def test_plan_vehicle_declares_the_fields(self):
        wire = PlanVehicle(type="Bici", quantity=1, priority_vehicle=1, service_time_min=0.25).model_dump(exclude_none=True)
        self.assertEqual(wire["service_time_min"], 0.25)


if __name__ == "__main__":
    unittest.main()
