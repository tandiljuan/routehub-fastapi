import unittest
from types import SimpleNamespace

from libs.optimizer.models.draft_set import draft_routing_from_lot
from libs.lot_plan_adapter import build_plan_clustering, build_plan_routing
from libs.plan_build import build_plan_context_for_lot
from libs.plan_engine_defaults import (
    engine_routing_defaults,
    strip_engine_keys_from_config,
)
from libs.plan_wire import plan_to_wire_payload
from models.lot_config import ClusteringConfig, LotConfig, RoutingConfig, config_to_lot_config


def _lot_db_stub():
    return SimpleNamespace(
        route_stops_min=10,
        route_stops_max=20,
        milestone=SimpleNamespace(
            location="+-34.5921966-58.4782933",
            name="DBO1",
        ),
    )


def _fleet_links(qty: int = 2):
    return [
        SimpleNamespace(
            quantity=qty,
            vehicle=SimpleNamespace(
                id=1,
                name="Van",
                volume=1000,
                volume_unit=None,
                weight=None,
                weight_unit=None,
                consumption=None,
                consumption_unit=None,
                engine_type=None,
            ),
            run_profile=None,
        ),
    ]


def _build_ctx(
    lot_config: LotConfig,
    *,
    delivery_count: int = 100,
    fleet_qty: int = 2,
):
    return build_plan_context_for_lot(
        lot_db=_lot_db_stub(),
        lot_config=lot_config,
        fleet_links=_fleet_links(fleet_qty),
        delivery_rows=[(i, "+-34.6-58.5", None) for i in range(delivery_count)],
        fallback_stops_min=10,
        fallback_stops_max=20,
        delivery_count=delivery_count,
    )


class TestStripEngineKeys(unittest.TestCase):
    def test_preserves_force_vehicles_fleet_match(self):
        raw = {
            "clustering": {
                "force_vehicles_fleet_match": True,
                "force_split_clusters": False,
                "min_size_cluster": 99,
            },
            "routing": {
                "avg_speed_kph": 55,
                "service_time_min": 2.5,
                "use_graph_travel_time": True,
                "nearby_threshold_m": 999,
                "two_opt_fast_mode": False,
            },
            "vehicles": {"defaults": {}},
        }
        stripped = strip_engine_keys_from_config(raw)
        self.assertEqual(stripped["clustering"], {"force_vehicles_fleet_match": True})
        self.assertEqual(
            stripped["routing"],
            {
                "avg_speed_kph": 55,
                "service_time_min": 2.5,
                "use_graph_travel_time": True,
            },
        )
        self.assertIn("vehicles", stripped)

    def test_config_to_lot_config_roundtrip(self):
        lot_config = config_to_lot_config(
            {
                "clustering": {"force_vehicles_fleet_match": True, "force_split_clusters": True},
                "routing": {
                    "service_time_min": 9,
                    "avg_speed_kph": 33,
                    "use_graph_travel_time": True,
                    "nearby_threshold_m": 1,
                },
            }
        )
        self.assertIsNotNone(lot_config)
        self.assertIsNotNone(lot_config.clustering)
        self.assertTrue(lot_config.clustering.force_vehicles_fleet_match)
        self.assertIsNone(lot_config.clustering.model_dump().get("force_split_clusters"))
        self.assertIsNotNone(lot_config.routing)
        self.assertEqual(lot_config.routing.service_time_min, 9)
        self.assertEqual(lot_config.routing.avg_speed_kph, 33)
        self.assertTrue(lot_config.routing.use_graph_travel_time)
        self.assertIsNone(lot_config.routing.model_dump().get("nearby_threshold_m"))

    def test_false_flag_is_preserved(self):
        lot_config = config_to_lot_config(
            {"clustering": {"force_vehicles_fleet_match": False}}
        )
        self.assertIsNotNone(lot_config.clustering)
        self.assertFalse(lot_config.clustering.force_vehicles_fleet_match)


class TestDraftRoutingFromLot(unittest.TestCase):
    def test_true_flag_and_speed_are_sent(self):
        lot = LotConfig(
            routing=RoutingConfig(use_graph_travel_time=True, avg_speed_kph=32)
        )
        dumped = draft_routing_from_lot(lot).model_dump(exclude_none=True)
        self.assertTrue(dumped["use_graph_travel_time"])
        self.assertEqual(dumped["avg_speed_kph"], 32)
        self.assertNotIn("service_time_min", dumped)

    def test_false_flag_is_sent_not_omitted(self):
        lot = LotConfig(routing=RoutingConfig(use_graph_travel_time=False))
        dumped = draft_routing_from_lot(lot).model_dump(exclude_none=True)
        self.assertIn("use_graph_travel_time", dumped)
        self.assertFalse(dumped["use_graph_travel_time"])

    def test_omitted_flag_stays_off_the_wire(self):
        dumped = draft_routing_from_lot(LotConfig()).model_dump(exclude_none=True)
        self.assertNotIn("use_graph_travel_time", dumped)
        self.assertNotIn("avg_speed_kph", dumped)


class TestClientRoutingOverrides(unittest.TestCase):
    def test_build_plan_routing_merges_client_eta_fields(self):
        engine = engine_routing_defaults()
        lot_config = LotConfig(
            routing=RoutingConfig(service_time_min=3.5, avg_speed_kph=28),
        )
        plan_routing = build_plan_routing(lot_config, engine_routing=engine)
        self.assertEqual(plan_routing.service_time_min, 3.5)
        self.assertEqual(plan_routing.avg_speed_kph, 28)
        # Engine tuning stays unset: the optimizer applies its own defaults.
        self.assertIsNone(plan_routing.nearby_threshold_m)

    def test_build_plan_routing_lot_travel_time_wins_over_engine_default(self):
        engine = engine_routing_defaults()
        lot_config = LotConfig(routing=RoutingConfig(use_graph_travel_time=True))
        plan_routing = build_plan_routing(lot_config, engine_routing=engine)
        self.assertTrue(plan_routing.use_graph_travel_time)

    def test_false_graph_travel_time_is_preserved(self):
        lot_config = config_to_lot_config({"routing": {"use_graph_travel_time": False}})
        self.assertIsNotNone(lot_config.routing)
        self.assertFalse(lot_config.routing.use_graph_travel_time)

    def test_lot_false_wins_over_an_engine_default_true(self):
        # Proves false travels as a value: dropping it as "unset" would keep the engine's true.
        engine = {**engine_routing_defaults(), "use_graph_travel_time": True}
        lot_config = LotConfig(routing=RoutingConfig(use_graph_travel_time=False))
        self.assertFalse(build_plan_routing(lot_config, engine_routing=engine).use_graph_travel_time)

    def test_optimizer_wire_carries_the_flag_both_ways(self):
        # Web lot body -> stored lot config -> the request RouteHub sends to the optimizer.
        for enabled in (True, False):
            with self.subTest(enabled=enabled):
                lot_config = config_to_lot_config({"routing": {"use_graph_travel_time": enabled, "avg_speed_kph": 30}})
                wire = plan_to_wire_payload(_build_ctx(lot_config))
                self.assertIs(wire["routing"]["use_graph_travel_time"], enabled)
                self.assertEqual(wire["routing"]["avg_speed_kph"], 30)

    def test_optimizer_wire_omits_the_flag_when_the_lot_omits_it(self):
        # The optimizer applies its own default (false).
        wire = plan_to_wire_payload(_build_ctx(LotConfig()))
        self.assertNotIn("use_graph_travel_time", wire.get("routing") or {})


class TestPlanClusteringMerge(unittest.TestCase):
    def test_lot_force_fleet_match_overrides_engine_default(self):
        lot_config = LotConfig(clustering=ClusteringConfig(force_vehicles_fleet_match=True))
        ctx = _build_ctx(lot_config)
        self.assertTrue(ctx.clustering.force_vehicles_fleet_match)

    def test_lot_false_overrides_engine_default(self):
        lot_config = LotConfig(clustering=ClusteringConfig(force_vehicles_fleet_match=False))
        ctx = _build_ctx(lot_config)
        self.assertFalse(ctx.clustering.force_vehicles_fleet_match)

    def test_lot_omitted_uses_engine_default(self):
        lot_config = LotConfig()
        ctx = _build_ctx(lot_config)
        self.assertFalse(ctx.clustering.force_vehicles_fleet_match)

    def test_wire_payload_includes_lot_clustering_flag(self):
        lot_config = LotConfig(clustering=ClusteringConfig(force_vehicles_fleet_match=True))
        ctx = _build_ctx(lot_config)
        wire = plan_to_wire_payload(ctx)
        self.assertTrue(wire["clustering"]["force_vehicles_fleet_match"])

    def test_wire_leaves_sizes_split_and_batch_to_the_optimizer(self):
        # The optimizer computes them from stops and fleet (dynamic-fleet boost included).
        for force in (True, False):
            with self.subTest(force_vehicles_fleet_match=force):
                lot_config = LotConfig(clustering=ClusteringConfig(force_vehicles_fleet_match=force))
                wire = plan_to_wire_payload(_build_ctx(lot_config, delivery_count=8205, fleet_qty=57))
                for key in ("min_size_cluster", "max_size_cluster", "force_split_clusters", "size_cluster_tolerance"):
                    self.assertNotIn(key, wire["clustering"])
                self.assertNotIn("preprocessing_batch_size", wire["settings"].get("preprocessing") or {})
                self.assertNotIn("hardware", wire["settings"])

    def test_string_false_fleet_match_is_coerced(self):
        clustering = build_plan_clustering(engine_clustering={"force_vehicles_fleet_match": "false"})
        self.assertFalse(clustering.force_vehicles_fleet_match)

    def test_plan_clustering_json_override_still_reaches_the_wire(self):
        clustering = build_plan_clustering(engine_clustering={"size_cluster_tolerance": 0.2})
        self.assertEqual(clustering.model_dump(exclude_none=True)["size_cluster_tolerance"], 0.2)


if __name__ == "__main__":
    unittest.main()
