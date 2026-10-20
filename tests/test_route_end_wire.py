"""
Fin de la ruta (routing.route_end: "depot" | "last_stop") y cada ciudad en una sola pasada (routing.visit_zones_once):
el lote los guarda y llegan al optimizador; sin elegir nada no se manda ninguno (vuelve al depósito, como siempre).
"""
from __future__ import annotations

import os
import unittest

os.environ.setdefault("RDBMS_URL", "sqlite://")

from libs.lot_plan_adapter import build_plan_routing
from libs.optimizer.models.draft_set import draft_routing_from_lot
from libs.plan_engine_defaults import strip_engine_keys_from_config
from models.lot_config import LotConfig, RoutingConfig, config_to_lot_config


class TestRouteEnd(unittest.TestCase):
    def test_an_open_route_is_kept_on_the_lot_and_sent(self):
        lot = config_to_lot_config({"routing": {"route_end": "last_stop", "visit_zones_once": True}})
        self.assertEqual(lot.routing.route_end, "last_stop")
        routing = build_plan_routing(lot, engine_routing={}).model_dump(exclude_none=True)
        self.assertEqual(routing["route_end"], "last_stop")
        self.assertIs(routing["visit_zones_once"], True)

    def test_the_whitelist_keeps_both(self):
        stripped = strip_engine_keys_from_config(
            {"routing": {"route_end": "last_stop", "visit_zones_once": False, "api_type": "x"}})
        self.assertEqual(stripped, {"routing": {"route_end": "last_stop", "visit_zones_once": False}})

    def test_an_unknown_end_is_dropped_so_the_route_comes_back_to_the_depot(self):
        self.assertIsNone(RoutingConfig(route_end="anywhere").route_end)
        self.assertEqual(RoutingConfig(route_end="depot").route_end, "depot")

    def test_without_choosing_nothing_is_sent(self):
        routing = build_plan_routing(LotConfig(), engine_routing={}).model_dump(exclude_none=True)
        self.assertNotIn("route_end", routing)
        self.assertNotIn("visit_zones_once", routing)

    def test_a_false_visit_once_is_sent_as_false(self):
        lot = config_to_lot_config({"routing": {"visit_zones_once": False}})
        self.assertIs(build_plan_routing(lot, engine_routing={}).model_dump(exclude_none=True)["visit_zones_once"],
                      False)

    def test_a_reoptimization_keeps_the_route_end(self):
        lot = LotConfig(routing=RoutingConfig(route_end="last_stop", visit_zones_once=True))
        draft = draft_routing_from_lot(lot)
        self.assertEqual((draft.route_end, draft.visit_zones_once), ("last_stop", True))
        self.assertNotIn("route_end", draft_routing_from_lot(LotConfig()).model_dump(exclude_none=True))

    def test_an_end_point_travels_with_its_coordinates(self):
        lot = config_to_lot_config({"routing": {"route_end": "point", "route_end_point": {"lat": "34.05", "lng": -118.24}}})
        routing = build_plan_routing(lot, engine_routing={}).model_dump(exclude_none=True)
        self.assertEqual((routing["route_end"], routing["route_end_point"]), ("point", {"lat": 34.05, "lng": -118.24}))
        draft = draft_routing_from_lot(lot)
        self.assertEqual(draft.route_end_point, {"lat": 34.05, "lng": -118.24})

    def test_a_broken_end_point_is_dropped(self):
        self.assertIsNone(RoutingConfig(route_end="point", route_end_point={"lat": 95, "lng": 0}).route_end_point)
        self.assertIsNone(RoutingConfig(route_end="point", route_end_point="Los Angeles").route_end_point)


if __name__ == "__main__":
    unittest.main()
