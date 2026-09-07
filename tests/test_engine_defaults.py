import os
import unittest

os.environ.setdefault("RDBMS_URL", "sqlite://")

from libs.optimizer.models.plan_rebalance import PlanRebalance
from libs.optimizer.models.plan_routing import PlanRouting
from libs.plan_engine_defaults import _DEFAULT_ROUTING, resolve_engine_config


class TestEngineDefaultsAreIntentional(unittest.TestCase):
    """Pin the tuned optimizer defaults this branch introduced, so an
    accidental revert fails loudly rather than silently changing every plan."""

    def test_schedule_and_client_keys_are_not_in_engine_file(self):
        engine = resolve_engine_config()
        routing = engine["routing"]
        clustering = engine["clustering"]
        for key in (
            "optimize_time_windows",
            "start_time_minutes_route",
            "service_time_min",
            "avg_speed_kph",
            "early_tolerance_min",
            "late_tolerance_min",
        ):
            self.assertNotIn(key, routing)
        self.assertNotIn("force_vehicles_fleet_match", clustering)
        self.assertNotIn("force_split_clusters", clustering)

    def test_plan_routing_defaults_match_engine_dict(self):
        dumped = PlanRouting().model_dump(exclude_none=True)
        for key, value in _DEFAULT_ROUTING.items():
            self.assertIn(key, dumped)
            self.assertEqual(dumped[key], value, key)

    def test_preprocessing_batch_size_is_not_pinned(self):
        # Removed so the adapter's legacy formula (max_cluster * 4) drives it.
        engine = resolve_engine_config()
        self.assertNotIn("preprocessing_batch_size", engine["settings"]["preprocessing"])

    def test_rebalance_by_volume_off_by_default(self):
        # Wire default is off; lots opt in via config.rebalance.rebalance_by_volume.
        self.assertFalse(PlanRebalance().rebalance_by_volume)


if __name__ == "__main__":
    unittest.main()
