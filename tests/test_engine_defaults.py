import os
import unittest

os.environ.setdefault("RDBMS_URL", "sqlite://")

from libs.optimizer.models.plan_clustering import PlanClustering
from libs.optimizer.models.plan_rebalance import PlanRebalance
from libs.optimizer.models.plan_routing import PlanRouting
from libs.optimizer.models.plan_settings import PlanSettings
from libs.plan_engine_defaults import resolve_engine_config


class TestOptimizerOwnsEngineDefaults(unittest.TestCase):
    """The optimizer owns tuning defaults (route-optimizer-app src/helpers/engine_defaults.py):
    RouteHub must not pin its own set again, or channels drift apart."""

    def test_engine_file_carries_no_tuning(self):
        engine = resolve_engine_config()
        self.assertEqual(engine["clustering"], {})
        self.assertEqual(engine["routing"], {})
        self.assertEqual(engine["settings"].get("preprocessing") or {}, {})
        self.assertEqual(engine["settings"].get("hardware") or {}, {})

    def test_wire_models_send_no_tuning_by_default(self):
        self.assertEqual(PlanRouting().model_dump(exclude_none=True), {})
        self.assertEqual(
            PlanClustering().model_dump(exclude_none=True),
            {"strategy": "clustering", "force_vehicles_fleet_match": False},
        )
        self.assertEqual(PlanSettings().model_dump(exclude_none=True), {"preprocessing": {}})

    def test_rebalance_by_volume_off_by_default(self):
        # Wire default is off; lots opt in via config.rebalance.rebalance_by_volume.
        self.assertFalse(PlanRebalance().rebalance_by_volume)


if __name__ == "__main__":
    unittest.main()
