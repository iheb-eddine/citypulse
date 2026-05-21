"""Tests for observability module: health, metrics, middleware, alerts."""

import time
from collections import deque
from unittest.mock import patch

import pytest


class TestHealthEndpoint:
    def test_health_returns_200_with_structure(self, test_client):
        r = test_client.get("/health")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "healthy"
        assert "uptime_seconds" in data
        assert data["db"] == "ok"
        assert "timestamp" in data

    def test_health_db_error(self, test_client):
        with patch("app.observability.text") as mock_text:
            mock_text.side_effect = Exception("DB down")
            r = test_client.get("/health")
        assert r.status_code == 503
        assert r.json()["db"] == "error"
        assert r.json()["status"] == "degraded"


class TestMetricsEndpoint:
    def test_metrics_returns_structure(self, test_client):
        # Make a request first to populate metrics
        test_client.get("/health")
        r = test_client.get("/metrics")
        assert r.status_code == 200
        data = r.json()
        assert "request_count" in data
        assert "error_count" in data
        assert "error_rate" in data
        assert "endpoints" in data

    def test_metrics_api_key_protection(self, test_client):
        with patch("app.observability._METRICS_API_KEY", "secret123"):
            r = test_client.get("/metrics")
            assert r.status_code == 403
            r = test_client.get("/metrics?key=secret123")
            assert r.status_code == 200
            r = test_client.get("/metrics", headers={"x-api-key": "secret123"})
            assert r.status_code == 200


class TestMiddleware:
    def test_request_id_generated(self, test_client):
        r = test_client.get("/health")
        assert "x-request-id" in r.headers
        assert len(r.headers["x-request-id"]) > 0

    def test_request_id_passthrough(self, test_client):
        r = test_client.get("/health", headers={"x-request-id": "my-custom-id"})
        assert r.headers["x-request-id"] == "my-custom-id"

    def test_middleware_does_not_swallow_errors(self, test_client):
        """Middleware must not catch exceptions from route handlers."""
        r = test_client.get("/api/reports/99999/status")
        # This should still return the app's normal error, not 500 from middleware
        assert r.status_code in (404, 405)


class TestMetricsStore:
    def test_percentile_computation(self):
        from app.observability import MetricsStore
        store = MetricsStore()
        # Record 100 requests with known latencies
        for i in range(1, 101):
            store.record("/test", 200, float(i))
        snap = store.snapshot()
        ep = snap["endpoints"]["/test"]
        assert ep["p50"] == 51.0
        assert ep["p95"] == 96.0
        assert ep["p99"] == 100.0

    def test_error_rate_windowed(self):
        from app.observability import MetricsStore
        store = MetricsStore()
        # All requests are errors
        for _ in range(10):
            store.record("/test", 500, 1.0)
        assert store.get_error_rate() == 1.0
        # Add successful requests
        for _ in range(90):
            store.record("/test", 200, 1.0)
        rate = store.get_error_rate()
        assert 0.09 <= rate <= 0.11  # ~10%


class TestAlertMechanism:
    def test_alert_fires_on_high_error_rate(self):
        from app.observability import MetricsStore
        store = MetricsStore()
        # Generate >10% error rate
        for _ in range(20):
            store.record("/test", 500, 1.0)
        for _ in range(10):
            store.record("/test", 200, 1.0)
        with patch("app.observability.logger") as mock_logger:
            fired = store.check_alert()
        assert fired is True
        mock_logger.critical.assert_called_once()

    def test_alert_cooldown(self):
        from app.observability import MetricsStore
        store = MetricsStore()
        for _ in range(20):
            store.record("/test", 500, 1.0)
        with patch("app.observability.logger"):
            store.check_alert()
            # Second call within cooldown should not fire
            fired = store.check_alert()
        assert fired is False
