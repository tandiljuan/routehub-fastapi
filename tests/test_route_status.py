import os
import unittest
from unittest.mock import MagicMock, patch

import requests

os.environ.setdefault("RDBMS_URL", "sqlite://")

from libs.optimizer.models.route_status import RouteStatus
from libs.optimizer.optimizer import Optimizer, OptimizerError


class TestRouteStatusModel(unittest.TestCase):
    def test_parses_optimizer_status_payload(self):
        payload = {
            "details": {
                "clustering": {"completed_chunks": 6, "total_chunks": 6},
                "graphs": {
                    "active_downloads": 1,
                    "completed_downloads": 1,
                    "disk_loads": 0,
                    "redis_hits": 0,
                },
                "routing": {"completed_routes": 0, "total_routes": 60},
            },
            "elapsed_seconds": 142,
            "message": "Downloading map data (1 completed, 1 in progress).",
            "phase": "downloading_graphs",
            "phase_label": "Downloading map data",
            "progress_pct": 38,
            "session_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
            "status": "processing",
            "steps": [
                {"id": "queued", "label": "Waiting for server capacity", "state": "done"},
                {"id": "routing", "label": "Calculating route sequences", "state": "pending"},
            ],
        }
        status = RouteStatus.model_validate(payload)
        self.assertEqual(status.status, "processing")
        self.assertEqual(status.progress_pct, 38)
        self.assertEqual(status.details.routing.total_routes, 60)
        self.assertEqual(len(status.steps), 2)


class TestOptimizerRouteStatus(unittest.TestCase):
    @patch("libs.optimizer.optimizer.requests.get")
    def test_get_route_status_proxies_optimizer(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "session_id": "sess-1",
            "status": "processing",
            "progress_pct": 10,
        }
        mock_get.return_value = mock_response

        opt = Optimizer("http://optimizer", 8000, "secret")
        status_code, body = opt.get_route_status("sess-1")

        self.assertEqual(status_code, 200)
        self.assertEqual(body["session_id"], "sess-1")
        mock_get.assert_called_once_with(
            "http://optimizer:8000/route-optimizer-app/routes/sess-1/status",
            headers={"api-key": "secret"},
            # (connect, read). The 30s read budget this test has always pinned is
            # kept — a status poll must fail fast rather than hang; the connect
            # bound is new (an unreachable optimizer used to block indefinitely).
            timeout=(10, 30),
        )


class TestOptimizerTransportFailures(unittest.TestCase):
    """An unreachable optimizer must surface as OptimizerError, not as a raw
    requests exception. Routes translate OptimizerError into a 502; anything
    else escapes the handler as a 500 with a traceback, which is what
    `GET /lots/{id}/plan` did when host.docker.internal briefly went away."""

    def _assert_wraps(self, call):
        opt = Optimizer("http://optimizer", 8000, "secret")
        for exc in (
            requests.ConnectionError("Network unreachable"),
            requests.ReadTimeout("timed out"),
        ):
            with patch("libs.optimizer.optimizer.requests.get", side_effect=exc):
                with self.assertRaises(OptimizerError) as ctx:
                    call(opt)
                self.assertIn("Optimizer unreachable", str(ctx.exception))

    def test_get_route_status_wraps_transport_errors(self):
        self._assert_wraps(lambda o: o.get_route_status("sess-1"))

    def test_get_plan_result_wraps_transport_errors(self):
        self._assert_wraps(lambda o: o.get_plan_result("task-1"))

    def test_get_draft_result_wraps_transport_errors(self):
        self._assert_wraps(lambda o: o.get_draft_result("task-1"))

    def test_send_route_plan_still_wraps_transport_errors(self):
        opt = Optimizer("http://optimizer", 8000, "secret")
        with patch(
            "libs.optimizer.optimizer.requests.post",
            side_effect=requests.ConnectionError("Network unreachable"),
        ):
            with self.assertRaises(OptimizerError):
                opt._post_session("http://optimizer:8000/x", {})


if __name__ == "__main__":
    unittest.main()
