import os
import unittest

os.environ.setdefault("RDBMS_URL", "sqlite://")

from libs.lot_persistence import (
    _route_data_from_optimizer,
    _totals_data_from_result,
    delivery_links_for_route,
    serialize_plan_poll,
)
from libs.optimizer.models import ResultRoute, ResultSet, ResultTotal, ResultWaypoint
from libs.optimizer.models.result_waypoint import ResultPackage
from libs.time_window_wire import normalize_time_window, normalize_waypoint_payload
from models.delivery_plan import _coerce_delivery_id
from models.enum import DeliveryLotState


class TestSerializePlanPoll(unittest.TestCase):
    def test_includes_optimizer_session_id(self):
        payload = serialize_plan_poll(DeliveryLotState.PROCESSING, "sess-abc")
        self.assertEqual(payload["state"], DeliveryLotState.PROCESSING)
        self.assertEqual(payload["session_id"], "sess-abc")
        self.assertEqual(payload["optimizer_session_id"], "sess-abc")
        self.assertIsNone(payload["routes"])


class TestTotalsFromResult(unittest.TestCase):
    def test_merges_root_rejection_fields_and_unserved(self):
        result = ResultSet(
            totals=ResultTotal(total_routes=57, total_points=8202),
            submitted_points=8205,
            rejection_summary={"capacity": 3},
            rejected_deliveries=[{"delivery_id": "1", "reason": "capacity"}],
        )
        data = _totals_data_from_result(result)
        self.assertEqual(data["submitted_points"], 8205)
        self.assertEqual(data["total_points"], 8202)
        self.assertEqual(data["unserved_points"], 3)
        self.assertEqual(data["rejection_summary"], {"capacity": 3})
        self.assertEqual(len(data["rejected_deliveries"]), 1)


class TestCoerceDeliveryId(unittest.TestCase):
    def test_parses_numeric_strings(self):
        self.assertEqual(_coerce_delivery_id("42"), 42)
        self.assertEqual(_coerce_delivery_id(42), 42)

    def test_rejects_non_numeric(self):
        self.assertIsNone(_coerce_delivery_id("pkg-42"))
        self.assertIsNone(_coerce_delivery_id(""))
        self.assertIsNone(_coerce_delivery_id(None))


class TestTimeWindowWire(unittest.TestCase):
    def test_normalizes_minute_pair_list(self):
        self.assertEqual(
            normalize_time_window([780, 1200]),
            {"start_minutes": 780, "end_minutes": 1200},
        )

    def test_normalizes_waypoint_payload(self):
        wp = normalize_waypoint_payload({
            "order": 1,
            "time_window": [780, 1260],
            "packages": [{"package_id": "1", "time_window": [660, 1500]}],
        })
        self.assertEqual(wp["time_window"], {"start_minutes": 780, "end_minutes": 1260})
        self.assertEqual(
            wp["packages"][0]["time_window"],
            {"start_minutes": 660, "end_minutes": 1500},
        )


class TestRouteDataFromOptimizer(unittest.TestCase):
    def test_includes_waypoints_with_arrival_time(self):
        route = ResultRoute(
            route_geometry=[[-34.6, -58.5]],
            optimized_waypoints=[
                ResultWaypoint(
                    order=1,
                    lat=-34.6,
                    lng=-58.5,
                    arrival_time=540.5,
                    time_window=[780, 1200],
                    packages=[ResultPackage(package_id="pkg-42")],
                ),
            ],
        )
        data = _route_data_from_optimizer(
            route,
            0,
            package_to_delivery={"pkg-42": 42},
        )
        self.assertIn("optimized_waypoints", data)
        wp = data["optimized_waypoints"][0]
        self.assertEqual(wp["delivery_id"], "42")
        self.assertEqual(wp["arrival_time"], 540.5)
        self.assertEqual(wp["time_window"], {"start_minutes": 780, "end_minutes": 1200})
        self.assertEqual(data["arrival_times"], [540.5])
        self.assertEqual(data["stops"], data["optimized_waypoints"])


class TestMergedWaypointMultiDelivery(unittest.TestCase):
    """A single waypoint can bundle packages from several deliveries."""

    def _route(self):
        return ResultRoute(
            route_id="1",
            route_geometry=[[-34.6, -58.5]],
            optimized_waypoints=[
                ResultWaypoint(
                    order=1,
                    lat=-34.6,
                    lng=-58.5,
                    arrival_time=600,
                    packages=[
                        ResultPackage(package_id="pkg-10"),
                        ResultPackage(package_id="pkg-20"),
                    ],
                ),
            ],
        )

    def test_links_every_delivery_at_the_shared_waypoint(self):
        links = delivery_links_for_route(
            7, self._route(), {"pkg-10": 10, "pkg-20": 20}
        )
        self.assertEqual({link.delivery_id for link in links}, {10, 20})
        self.assertTrue(all(link.delivery_path_id == 7 for link in links))

    def test_merged_waypoint_produces_unique_delivery_orders(self):
        """Regresion: (delivery_path_id, delivery_order) tiene constraint UNIQUE.

        Un waypoint fusionado (varias deliveries en la misma coordenada) hacia
        que todas heredaran el mismo waypoint.order -> UniqueViolation al
        persistir (visto con el dataset de Boston/USSUFFOLK, lot 84).
        Los orders deben re-enumerarse secuencialmente preservando la visita.
        """
        route = ResultRoute(
            route_id="1",
            route_geometry=[[-34.6, -58.5]],
            optimized_waypoints=[
                ResultWaypoint(
                    order=1,
                    lat=-34.6,
                    lng=-58.5,
                    packages=[
                        ResultPackage(package_id="pkg-10"),
                        ResultPackage(package_id="pkg-20"),  # misma coordenada
                    ],
                ),
                ResultWaypoint(
                    order=2,
                    lat=-34.7,
                    lng=-58.6,
                    packages=[ResultPackage(package_id="pkg-30")],
                ),
            ],
        )
        links = delivery_links_for_route(
            7, route, {"pkg-10": 10, "pkg-20": 20, "pkg-30": 30}
        )
        orders = [link.delivery_order for link in links]
        self.assertEqual(len(orders), len(set(orders)), "delivery_order duplicado")
        self.assertEqual(sorted(orders), list(range(1, len(orders) + 1)))
        # La delivery del segundo waypoint visita despues de las del primero
        by_delivery = {link.delivery_id: link.delivery_order for link in links}
        self.assertGreater(by_delivery[30], by_delivery[10])
        self.assertGreater(by_delivery[30], by_delivery[20])

    def test_payload_exposes_all_delivery_ids(self):
        data = _route_data_from_optimizer(
            self._route(), 0, package_to_delivery={"pkg-10": 10, "pkg-20": 20}
        )
        wp = data["optimized_waypoints"][0]
        self.assertEqual(wp["delivery_id"], "10")  # backward-compatible first id
        self.assertEqual(wp["delivery_ids"], ["10", "20"])


if __name__ == "__main__":
    unittest.main()
