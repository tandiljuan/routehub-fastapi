import os
import unittest

os.environ.setdefault("RDBMS_URL", "sqlite://")

from libs.optimizer.models.plan_rebalance import PlanRebalance
from libs.optimizer.models.plan_routing import PlanRouting
from libs.plan_engine_defaults import resolve_engine_config


class TestEngineDefaultsAreIntentional(unittest.TestCase):
    """Pin the tuned optimizer defaults this branch introduced, so an
    accidental revert fails loudly rather than silently changing every plan."""

    def test_routing_start_time_minutes(self):
        engine = resolve_engine_config()
        self.assertEqual(engine["routing"]["start_time_minutes_route"], 800)
        self.assertEqual(PlanRouting().start_time_minutes_route, 800)

    def test_force_split_clusters_off_by_default(self):
        # Recomputed per-plan from force_vehicles_fleet_match; default base is off.
        engine = resolve_engine_config()
        self.assertFalse(engine["clustering"]["force_split_clusters"])

    def test_preprocessing_batch_size_is_not_pinned(self):
        # Removed so the adapter's legacy formula (max_cluster * 4) drives it.
        engine = resolve_engine_config()
        self.assertNotIn("preprocessing_batch_size", engine["settings"]["preprocessing"])

    def test_rebalance_by_volume_on_by_default(self):
        self.assertTrue(PlanRebalance().rebalance_by_volume)


if __name__ == "__main__":
    unittest.main()
