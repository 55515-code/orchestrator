"""Dashboard service for real-time Substrate blockchain monitoring.

Provides metrics collection, Prometheus exposition, and visualization
for node health, chain metrics, and deployment status.
"""

from .api import create_dashboard_router
from .metrics import DashboardMetrics, get_metrics_registry

__all__ = [
    "DashboardMetrics",
    "create_dashboard_router",
    "get_metrics_registry",
]
