import math
import unittest
from types import SimpleNamespace

from libs.lot_plan_adapter import (
    build_plan_clustering,
    compute_cluster_sizes,
    scale_cluster_sizes_for_dynamic_fleet,
)
from libs.plan_build import build_plan_context_for_lot
from libs.plan_engine_defaults import (
    DYNAMIC_FLEET_CLUSTER_BOOST_2K_TO_5K,
    DYNAMIC_FLEET_CLUSTER_BOOST_ABOVE_5K,
    dynamic_fleet_cluster_size_boost,
    engine_clustering_defaults,
    strip_engine_keys_from_config,
)
from libs.plan_wire import plan_to_wire_payload
from models.lot_config import ClusteringConfig, LotConfig, config_to_lot_config


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


class TestDynamicFleetBoostTiers(unittest.TestCase):
    def test_up_to_2k_stops_no_boost(self):
        self.assertEqual(dynamic_fleet_cluster_size_boost(0), 1.0)
        self.assertEqual(dynamic_fleet_cluster_size_boost(2000), 1.0)

    def test_between_2k_and_5k_stops_uses_115(self):
        self.assertEqual(dynamic_fleet_cluster_size_boost(2001), DYNAMIC_FLEET_CLUSTER_BOOST_2K_TO_5K)
        self.assertEqual(dynamic_fleet_cluster_size_boost(5000), DYNAMIC_FLEET_CLUSTER_BOOST_2K_TO_5K)

    def test_above_5k_stops_uses_125(self):
        self.assertEqual(dynamic_fleet_cluster_size_boost(5001), DYNAMIC_FLEET_CLUSTER_BOOST_ABOVE_5K)
        self.assertEqual(dynamic_fleet_cluster_size_boost(8205), DYNAMIC_FLEET_CLUSTER_BOOST_ABOVE_5K)


class TestStripEngineKeys(unittest.TestCase):
    def test_preserves_force_vehicles_fleet_match(self):
        raw = {
            "clustering": {
                "force_vehicles_fleet_match": True,
                "force_split_clusters": False,
                "min_size_cluster": 99,
            },
            "routing": {"avg_speed_kph": 55},
            "vehicles": {"defaults": {}},
        }
        stripped = strip_engine_keys_from_config(raw)
        self.assertEqual(stripped["clustering"], {"force_vehicles_fleet_match": True})
        self.assertNotIn("routing", stripped)
        self.assertIn("vehicles", stripped)

    def test_config_to_lot_config_roundtrip(self):
        lot_config = config_to_lot_config(
            {
                "clustering": {"force_vehicles_fleet_match": True, "force_split_clusters": True},
                "routing": {"service_time_min": 9},
            }
        )
        self.assertIsNotNone(lot_config)
        self.assertIsNotNone(lot_config.clustering)
        self.assertTrue(lot_config.clustering.force_vehicles_fleet_match)
        self.assertIsNone(lot_config.clustering.model_dump().get("force_split_clusters"))

    def test_false_flag_is_preserved(self):
        lot_config = config_to_lot_config(
            {"clustering": {"force_vehicles_fleet_match": False}}
        )
        self.assertIsNotNone(lot_config.clustering)
        self.assertFalse(lot_config.clustering.force_vehicles_fleet_match)


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

    def test_server_owned_clustering_keys_unchanged_by_lot(self):
        lot_config = LotConfig(clustering=ClusteringConfig(force_vehicles_fleet_match=True))
        ctx = _build_ctx(lot_config)
        self.assertFalse(ctx.clustering.force_split_clusters)

    def test_dynamic_fleet_enables_force_split_clusters(self):
        lot_config = LotConfig(clustering=ClusteringConfig(force_vehicles_fleet_match=False))
        ctx = _build_ctx(lot_config)
        self.assertTrue(ctx.clustering.force_split_clusters)

    def test_omitted_force_fleet_match_defaults_to_dynamic_split(self):
        lot_config = LotConfig()
        ctx = _build_ctx(lot_config)
        self.assertFalse(ctx.clustering.force_vehicles_fleet_match)
        self.assertTrue(ctx.clustering.force_split_clusters)

    def test_wire_payload_includes_lot_clustering_flag(self):
        lot_config = LotConfig(clustering=ClusteringConfig(force_vehicles_fleet_match=True))
        ctx = _build_ctx(lot_config)
        wire = plan_to_wire_payload(ctx)
        self.assertTrue(wire["clustering"]["force_vehicles_fleet_match"])

    def test_dynamic_fleet_up_to_2k_keeps_base_cluster_sizes(self):
        lot_config = LotConfig(clustering=ClusteringConfig(force_vehicles_fleet_match=False))
        ctx = _build_ctx(lot_config, delivery_count=100)
        base_min, base_max = compute_cluster_sizes(100, 2)
        self.assertEqual(ctx.clustering.min_size_cluster, base_min)
        self.assertEqual(ctx.clustering.max_size_cluster, base_max)

    def test_dynamic_fleet_at_2k_keeps_base_cluster_sizes(self):
        lot_config = LotConfig(clustering=ClusteringConfig(force_vehicles_fleet_match=False))
        ctx = _build_ctx(lot_config, delivery_count=2000)
        base_min, base_max = compute_cluster_sizes(2000, 2)
        self.assertEqual(ctx.clustering.min_size_cluster, base_min)
        self.assertEqual(ctx.clustering.max_size_cluster, base_max)

    def test_dynamic_fleet_between_2k_and_5k_boosts_by_115(self):
        lot_config = LotConfig(clustering=ClusteringConfig(force_vehicles_fleet_match=False))
        delivery_count = 3000
        ctx = _build_ctx(lot_config, delivery_count=delivery_count)
        base_min, base_max = compute_cluster_sizes(delivery_count, 2)
        expected_min, expected_max = scale_cluster_sizes_for_dynamic_fleet(
            base_min,
            base_max,
            delivery_count=delivery_count,
        )
        self.assertEqual(ctx.clustering.min_size_cluster, expected_min)
        self.assertEqual(ctx.clustering.max_size_cluster, expected_max)
        self.assertEqual(expected_min, math.ceil(base_min * 1.15))
        self.assertEqual(expected_max, math.ceil(base_max * 1.15))

    def test_force_fleet_match_keeps_base_auto_cluster_sizes(self):
        lot_config = LotConfig(clustering=ClusteringConfig(force_vehicles_fleet_match=True))
        ctx = _build_ctx(lot_config, delivery_count=8205)
        base_min, base_max = compute_cluster_sizes(8205, 2)
        self.assertEqual(ctx.clustering.min_size_cluster, base_min)
        self.assertEqual(ctx.clustering.max_size_cluster, base_max)

    def test_dbo1_scale_example_71_142_becomes_89_178_when_dynamic(self):
        """8205 stops ÷ 58 vehicles → 71/142 base; +25% tier → 89/178."""
        base_min, base_max = compute_cluster_sizes(8205, 58)
        self.assertEqual(base_min, 71)
        self.assertEqual(base_max, 142)
        boosted = build_plan_clustering(
            engine_clustering={
                **engine_clustering_defaults(),
                "force_vehicles_fleet_match": False,
            },
            a_sum=8205,
            v_sum=58,
        )
        self.assertEqual(boosted.min_size_cluster, 89)
        self.assertEqual(boosted.max_size_cluster, 178)

    def test_dynamic_fleet_boosts_even_when_engine_presets_cluster_sizes(self):
        """PLAN_CLUSTERING_JSON may pre-fill min/max — dynamic fleet must still boost."""
        base_min, base_max = compute_cluster_sizes(8205, 57)
        self.assertEqual(base_min, 72)
        self.assertEqual(base_max, 144)
        boosted = build_plan_clustering(
            engine_clustering={
                **engine_clustering_defaults(),
                "min_size_cluster": base_min,
                "max_size_cluster": base_max,
                "force_vehicles_fleet_match": False,
            },
            a_sum=8205,
            v_sum=57,
        )
        self.assertEqual(boosted.min_size_cluster, 90)
        self.assertEqual(boosted.max_size_cluster, 180)

    def test_string_false_applies_dynamic_fleet_boost(self):
        boosted = build_plan_clustering(
            engine_clustering={
                **engine_clustering_defaults(),
                "force_vehicles_fleet_match": "false",
            },
            a_sum=8205,
            v_sum=58,
        )
        self.assertEqual(boosted.min_size_cluster, 89)
        self.assertEqual(boosted.max_size_cluster, 178)
        self.assertTrue(boosted.force_split_clusters)

    def test_ui_run_57_vehicles_dynamic_fleet_wire_sizes(self):
        lot_config = LotConfig(clustering=ClusteringConfig(force_vehicles_fleet_match=False))
        ctx = _build_ctx(lot_config, delivery_count=8205, fleet_qty=57)
        self.assertEqual(ctx.clustering.min_size_cluster, 90)
        self.assertEqual(ctx.clustering.max_size_cluster, 180)


if __name__ == "__main__":
    unittest.main()
