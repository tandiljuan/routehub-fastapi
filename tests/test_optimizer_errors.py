import os
import unittest
from unittest.mock import MagicMock, patch

import requests

os.environ.setdefault("RDBMS_URL", "sqlite://")

from libs.optimizer.optimizer import Optimizer, OptimizerError


class TestOptimizerSessionErrors(unittest.TestCase):
    @patch("libs.optimizer.optimizer.plan_to_wire_payload", return_value={"addresses": []})
    @patch("libs.optimizer.optimizer.requests.post")
    def test_missing_session_id_raises_optimizer_error(self, mock_post, _mock_payload):
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 200
        mock_response.json.return_value = {"detail": "something went wrong"}
        mock_post.return_value = mock_response

        opt = Optimizer("http://optimizer", 8000, "secret")
        with self.assertRaises(OptimizerError) as ctx:
            opt.send_route_plan(plan=MagicMock())

        self.assertIn("missing session_id", str(ctx.exception))
        self.assertEqual(ctx.exception.upstream_status, 200)

    @patch("libs.optimizer.optimizer.requests.post")
    def test_upstream_error_includes_status_and_detail(self, mock_post):
        draft = MagicMock()
        draft.model_dump.return_value = {"routes": []}
        mock_response = MagicMock()
        mock_response.ok = False
        mock_response.status_code = 401
        mock_response.json.return_value = {"detail": "Invalid API key"}
        mock_post.return_value = mock_response

        opt = Optimizer("http://optimizer", 8000, "secret")
        with self.assertRaises(OptimizerError) as ctx:
            opt.send_route_draft(draft=draft)

        self.assertIn("HTTP 401", str(ctx.exception))
        self.assertIn("Invalid API key", str(ctx.exception))
        self.assertEqual(ctx.exception.upstream_status, 401)

    @patch("libs.optimizer.optimizer.plan_to_wire_payload", return_value={"addresses": []})
    @patch("libs.optimizer.optimizer.requests.post")
    def test_connection_error_raises_optimizer_error(self, mock_post, _mock_payload):
        mock_post.side_effect = requests.ConnectionError("connection refused")

        opt = Optimizer("http://optimizer", 8000, "secret")
        with self.assertRaises(OptimizerError) as ctx:
            opt.send_route_plan(plan=MagicMock())

        self.assertIn("unreachable", str(ctx.exception).lower())

    @patch("libs.optimizer.optimizer.plan_to_wire_payload", return_value={"addresses": []})
    @patch("libs.optimizer.optimizer.requests.post")
    def test_success_returns_session_id(self, mock_post, _mock_payload):
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.status_code = 202
        mock_response.json.return_value = {"session_id": "sess-abc"}
        mock_post.return_value = mock_response

        opt = Optimizer("http://optimizer", 8000, "secret")
        session_id = opt.send_route_plan(plan=MagicMock())

        self.assertEqual(session_id, "sess-abc")


if __name__ == "__main__":
    unittest.main()
