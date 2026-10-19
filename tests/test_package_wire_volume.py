"""A declared package volume (``volume_cm3``) without L/W/H must reach the optimizer.

The optimizer reads volume only from ``dimensions``; PlanPackage drops unknown keys. Before this,
a vepathos-orders.csv with a ``volume_cm3`` column produced routes with ``route_volume_cm3`` 0.
"""

from __future__ import annotations

import unittest

from libs.package_wire import build_plan_address, plan_packages_from_extra


def _volume(pkg) -> float:
    d = pkg.dimensions
    return d.length * d.width * d.height


class DeclaredVolumeTest(unittest.TestCase):
    def test_volume_only_becomes_equivalent_cube(self):
        [pkg] = plan_packages_from_extra(
            {"packages": [{"package_id": "NY-PKG-1001", "weight_kg": 20.8, "volume_cm3": 174787}]},
            fallback_package_id="1",
        )
        self.assertEqual(pkg.weight_kg, 20.8)
        self.assertIsNotNone(pkg.dimensions)
        self.assertEqual(pkg.dimensions.length, pkg.dimensions.width)
        self.assertEqual(pkg.dimensions.width, pkg.dimensions.height)
        self.assertLess(abs(_volume(pkg) - 174787) / 174787, 0.001)

    def test_full_dimensions_win_over_declared_volume(self):
        [pkg] = plan_packages_from_extra(
            {"packages": [{"package_id": "P", "volume_cm3": 999,
                           "dimensions": {"length": 30, "width": 20, "height": 10}}]},
            fallback_package_id="1",
        )
        self.assertEqual((pkg.dimensions.length, pkg.dimensions.width, pkg.dimensions.height), (30, 20, 10))

    def test_partial_dimensions_fall_back_to_declared_volume(self):
        [pkg] = plan_packages_from_extra(
            {"packages": [{"package_id": "P", "volume_cm3": 1000, "dimensions": {"length": 30}}]},
            fallback_package_id="1",
        )
        self.assertEqual(_volume(pkg), 1000)

    def test_no_volume_no_dimensions_stays_empty(self):
        for raw in (None, 0, -5, "abc"):
            [pkg] = plan_packages_from_extra(
                {"packages": [{"package_id": "P", "volume_cm3": raw}]}, fallback_package_id="1",
            )
            self.assertIsNone(pkg.dimensions, raw)

    def test_build_plan_address_carries_it(self):
        addr = build_plan_address(
            "+40.71-074.00/",
            {"lat": 40.71, "lng": -74.0, "packages": [{"package_id": "P", "volume_cm3": 8000}]},
            delivery_id=3,
        )
        self.assertEqual(_volume(addr.packages[0]), 8000)


if __name__ == "__main__":
    unittest.main()
