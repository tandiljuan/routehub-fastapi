"""U-turns and vehicle profile reach the optimizer: plan rule, vehicle type, route.

The optimizer resolves, per route: route > vehicle type > plan > its own default. RouteHub only has to
send what was configured, and nothing when nothing was (pydantic would otherwise drop undeclared fields,
and a forced null would hide the engine default).
"""

from __future__ import annotations

import os
import unittest
from types import SimpleNamespace

os.environ.setdefault("RDBMS_URL", "sqlite://")

from libs.lot_plan_adapter import build_plan_routing, build_plan_vehicles, vehicle_profile
from libs.optimizer.models.draft_route import DraftRoute
from libs.optimizer.models.draft_set import DraftSet, draft_routing_from_lot
from libs.optimizer.models.plan_routing import PlanRouting
from libs.optimizer.models.plan_vehicle import PlanVehicle
from libs.plan_engine_defaults import strip_engine_keys_from_config
from models.enum import VehicleCategoryType
from models.lot_config import LotConfig, RoutingConfig, config_to_lot_config


def _link(*, name: str, category=None, allow_uturns=None) -> SimpleNamespace:
    return SimpleNamespace(
        quantity=1,
        alias=None,
        vehicle=SimpleNamespace(
            id=hash(name) % 1000,
            name=name,
            volume=None, volume_unit=None, weight=None, weight_unit=None,
            consumption=None, consumption_unit=None, engine_type=None,
            category_type=category,
            allow_uturns=allow_uturns,
        ),
        run_profile=None,
    )


def _lot_stub() -> SimpleNamespace:
    return SimpleNamespace(
        route_stops_min=None, route_stops_max=None,
        route_length_min=None, route_length_max=None, route_length_unit=None,
        route_time_min=None, route_time_max=None, route_time_unit=None,
    )


class TestPlanRule(unittest.TestCase):
    def test_the_plan_rule_is_kept_on_the_lot_and_sent(self):
        lot = config_to_lot_config({"routing": {"uturn_policy": "no_uturn", "two_opt_fast_mode": True}})
        self.assertEqual(lot.routing.uturn_policy, "no_uturn")
        self.assertEqual(build_plan_routing(lot, engine_routing={}).uturn_policy, "no_uturn")

    def test_the_whitelist_keeps_it(self):
        stripped = strip_engine_keys_from_config({"routing": {"uturn_policy": "allow", "api_type": "x"}})
        self.assertEqual(stripped, {"routing": {"uturn_policy": "allow"}})

    def test_an_unknown_rule_is_dropped_so_the_engine_default_applies(self):
        self.assertIsNone(RoutingConfig(uturn_policy="sometimes").uturn_policy)

    def test_without_a_rule_nothing_is_sent(self):
        routing = build_plan_routing(LotConfig(), engine_routing={})
        self.assertNotIn("uturn_policy", routing.model_dump(exclude_none=True))

    def test_a_reoptimization_carries_the_plan_rule(self):
        lot = LotConfig(routing=RoutingConfig(uturn_policy="no_uturn"))
        self.assertEqual(draft_routing_from_lot(lot).uturn_policy, "no_uturn")
        self.assertNotIn("uturn_policy", draft_routing_from_lot(LotConfig()).model_dump(exclude_none=True))


class TestVehicleType(unittest.TestCase):
    def test_a_bike_that_may_turn_around_says_so_and_rides_the_bike_network(self):
        [bike] = build_plan_vehicles([_link(name="Bici", category=VehicleCategoryType.BICYCLE, allow_uturns=True)], _lot_stub(), LotConfig())
        wire = bike.model_dump(exclude_none=True)
        self.assertEqual(wire["profile"], "bicycle")
        self.assertIs(wire["allow_uturns"], True)

    def test_false_is_a_real_value_and_is_sent(self):
        [van] = build_plan_vehicles([_link(name="Van", category=VehicleCategoryType.VAN, allow_uturns=False)], _lot_stub(), LotConfig())
        self.assertIs(van.model_dump(exclude_none=True)["allow_uturns"], False)

    def test_a_car_without_its_own_rule_sends_neither_field(self):
        [van] = build_plan_vehicles([_link(name="Van", category=VehicleCategoryType.VAN)], _lot_stub(), LotConfig())
        wire = van.model_dump(exclude_none=True)
        self.assertNotIn("profile", wire)
        self.assertNotIn("allow_uturns", wire)

    def test_profile_from_the_category(self):
        self.assertEqual(vehicle_profile(SimpleNamespace(category_type=VehicleCategoryType.BICYCLE)), "bicycle")
        self.assertEqual(vehicle_profile(SimpleNamespace(category_type="BICYCLE")), "bicycle")
        self.assertIsNone(vehicle_profile(SimpleNamespace(category_type=VehicleCategoryType.MOTORCYCLE)))
        self.assertIsNone(vehicle_profile(SimpleNamespace()))


class TestWireModels(unittest.TestCase):
    def test_declared_fields_serialize_and_none_is_omitted(self):
        self.assertEqual(PlanRouting(uturn_policy="allow").model_dump(exclude_none=True), {"uturn_policy": "allow"})
        vehicle = PlanVehicle(type="Bici", quantity=1, priority_vehicle=1, profile="bicycle", allow_uturns=True)
        self.assertEqual({k: v for k, v in vehicle.model_dump(exclude_none=True).items() if k in ("profile", "allow_uturns")},
                         {"profile": "bicycle", "allow_uturns": True})
        bare = PlanVehicle(type="Van", quantity=1, priority_vehicle=1).model_dump(exclude_none=True)
        self.assertNotIn("profile", bare)
        self.assertNotIn("allow_uturns", bare)

    def test_a_draft_route_carries_its_vehicle(self):
        route = DraftRoute(route_id="7", waypoints=[], profile="bicycle", allow_uturns=True)
        draft = DraftSet(origin_lat=0, origin_lng=0, tag="t", optimization_params=draft_routing_from_lot(None), routes=[route])
        wire = draft.model_dump(serialize_as_any=True, exclude_none=True)["routes"][0]
        self.assertEqual((wire["profile"], wire["allow_uturns"]), ("bicycle", True))
        plain = DraftRoute(route_id="8", waypoints=[]).model_dump(exclude_none=True)
        self.assertNotIn("allow_uturns", plain)


if __name__ == "__main__":
    unittest.main()
