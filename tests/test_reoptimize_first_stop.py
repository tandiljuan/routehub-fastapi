"""Reoptimizar con "empezar por esta parada": first_stop llega del pedido de la web a /routes/optimize."""
import os
import unittest

os.environ.setdefault("RDBMS_URL", "sqlite://")


class TestReoptimizeFirstStop(unittest.TestCase):
    def test_draft_route_sends_first_stop_only_when_set(self):
        from libs.optimizer.models.draft_route import DraftRoute

        plain = DraftRoute(route_id="1", waypoints=[]).model_dump(exclude_none=True)
        self.assertNotIn("first_stop", plain)
        pinned = DraftRoute(route_id="1", waypoints=[], first_stop={"lat": 53.3, "lng": -6.4})
        self.assertEqual(pinned.model_dump(exclude_none=True)["first_stop"], {"lat": 53.3, "lng": -6.4})

    def test_route_update_accepts_first_stop(self):
        from models.delivery_plan import DeliveryRouteUpdate

        self.assertIsNone(DeliveryRouteUpdate(id="1", deliveries=["a"]).first_stop)
        self.assertEqual(DeliveryRouteUpdate(id="1", deliveries=["a", "b"], first_stop="b").first_stop, "b")


if __name__ == "__main__":
    unittest.main()
