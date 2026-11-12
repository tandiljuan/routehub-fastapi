"""vepathos-bks-optimizer: client and configuration.

With BKS_OPTIMIZER_ENABLED=false (default) the lot's BKS routes answer 404 and nothing else changes.
"""
import os

from .client import BksOptimizer, BksOptimizerError

BKS_OPTIMIZER_ENABLED = os.environ.get("BKS_OPTIMIZER_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}
BKS_OPTIMIZER_URL = os.environ.get("BKS_OPTIMIZER_URL", "http://localhost:8815")
BKS_OPTIMIZER_API_KEY = os.environ.get("BKS_OPTIMIZER_API_KEY", "")
BKS_OPTIMIZER_TIMEOUT = float(os.environ.get("BKS_OPTIMIZER_TIMEOUT", "30"))


def client() -> BksOptimizer | None:
    """The configured client, or None when the integration is disabled."""
    if not BKS_OPTIMIZER_ENABLED:
        return None
    return BksOptimizer(BKS_OPTIMIZER_URL, BKS_OPTIMIZER_API_KEY, BKS_OPTIMIZER_TIMEOUT)


__all__ = ["BksOptimizer", "BksOptimizerError", "client"]
