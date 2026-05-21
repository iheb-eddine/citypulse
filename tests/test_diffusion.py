"""Tests for graph diffusion prediction."""

import numpy as np
import pytest

from app.diffusion import (
    haversine_km, build_adjacency, compute_diffusion,
    DIFFUSION_THRESHOLD_KM, DIFFUSIVITY, _get_centroids,
)
from app.models import Report


class TestHaversine:
    def test_same_point(self):
        assert haversine_km(48.78, 9.18, 48.78, 9.18) == 0.0

    def test_known_distance(self):
        # Stuttgart Hauptbahnhof to Bad Cannstatt ~2.5km
        d = haversine_km(48.784, 9.181, 48.804, 9.214)
        assert 2.0 < d < 4.0

    def test_symmetry(self):
        d1 = haversine_km(48.78, 9.18, 52.52, 13.40)
        d2 = haversine_km(52.52, 13.40, 48.78, 9.18)
        assert abs(d1 - d2) < 1e-10


class TestAdjacency:
    def test_self_no_edge(self):
        centroids = [("A", 48.78, 9.18), ("B", 48.79, 9.19)]
        A = build_adjacency(centroids)
        assert A[0, 0] == 0.0
        assert A[1, 1] == 0.0

    def test_close_nodes_connected(self):
        # Two points ~1.5km apart
        centroids = [("A", 48.780, 9.180), ("B", 48.790, 9.185)]
        A = build_adjacency(centroids)
        assert A[0, 1] == 1.0
        assert A[1, 0] == 1.0

    def test_far_nodes_disconnected(self):
        # Stuttgart to Berlin
        centroids = [("A", 48.78, 9.18), ("B", 52.52, 13.40)]
        A = build_adjacency(centroids)
        assert A[0, 1] == 0.0

    def test_symmetric(self):
        centroids = _get_centroids("stuttgart")
        A = build_adjacency(centroids)
        np.testing.assert_array_equal(A, A.T)


class TestComputeDiffusion:
    def test_zero_reports(self, db_session):
        result = compute_diffusion("stuttgart", 7, db_session)
        assert result["city"] == "stuttgart"
        assert result["horizon_days"] == 7
        assert all(p["predicted_rate"] == 0.0 for p in result["predictions"])
        assert result["graph"]["nodes"] == 17

    def test_with_reports(self, db_session):
        # Add a report in Hauptbahnhof area
        r = Report(
            photo_path="test.jpg", latitude=48.784, longitude=9.181,
            city="stuttgart", category="pothole", severity="high",
            department="roads", description="test", status="open",
        )
        db_session.add(r)
        db_session.commit()
        result = compute_diffusion("stuttgart", 7, db_session)
        # Hauptbahnhof should have current_reports=1
        hbf = next(p for p in result["predictions"] if p["neighborhood"] == "Hauptbahnhof")
        assert hbf["current_reports"] == 1
        # Predicted rate should be close to 1 but slightly less (diffusion spreads)
        assert 0.5 < hbf["predicted_rate"] <= 1.0
        # Some neighbor should have gained a small amount
        total_predicted = sum(p["predicted_rate"] for p in result["predictions"])
        assert abs(total_predicted - 1.0) < 0.05  # mass conservation (rounding tolerance)

    def test_resolved_excluded(self, db_session):
        r = Report(
            photo_path="test.jpg", latitude=48.784, longitude=9.181,
            city="stuttgart", category="pothole", severity="high",
            department="roads", description="test", status="resolved",
        )
        db_session.add(r)
        db_session.commit()
        result = compute_diffusion("stuttgart", 7, db_session)
        assert all(p["current_reports"] == 0 for p in result["predictions"])

    def test_different_horizons(self, db_session):
        r = Report(
            photo_path="test.jpg", latitude=48.784, longitude=9.181,
            city="stuttgart", category="pothole", severity="high",
            department="roads", description="test", status="open",
        )
        db_session.add(r)
        db_session.commit()
        r7 = compute_diffusion("stuttgart", 7, db_session)
        r30 = compute_diffusion("stuttgart", 30, db_session)
        # At t=30, more diffusion → source node has lower predicted rate
        hbf7 = next(p for p in r7["predictions"] if p["neighborhood"] == "Hauptbahnhof")
        hbf30 = next(p for p in r30["predictions"] if p["neighborhood"] == "Hauptbahnhof")
        assert hbf30["predicted_rate"] < hbf7["predicted_rate"]

    def test_graph_metadata(self, db_session):
        result = compute_diffusion("stuttgart", 7, db_session)
        assert result["graph"]["threshold_km"] == 3.0
        assert result["graph"]["edges"] > 0

    def test_berlin(self, db_session):
        result = compute_diffusion("berlin", 14, db_session)
        assert result["city"] == "berlin"
        assert result["graph"]["nodes"] == 8


class TestEndpoint:
    def test_default(self, test_client):
        resp = test_client.get("/api/predict/diffusion")
        assert resp.status_code == 200
        data = resp.json()
        assert data["city"] == "stuttgart"
        assert data["horizon_days"] == 7

    def test_with_city(self, test_client):
        resp = test_client.get("/api/predict/diffusion?city=berlin&horizon=14")
        assert resp.status_code == 200
        data = resp.json()
        assert data["city"] == "berlin"
        assert data["horizon_days"] == 14

    def test_invalid_horizon(self, test_client):
        resp = test_client.get("/api/predict/diffusion?horizon=5")
        assert resp.status_code == 400
        assert "horizon" in resp.json()["error"]

    def test_invalid_city_falls_back(self, test_client):
        resp = test_client.get("/api/predict/diffusion?city=invalid")
        assert resp.status_code == 200
        assert resp.json()["city"] == "stuttgart"
