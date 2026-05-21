"""Tests for crew dispatch optimization."""

import numpy as np
import pytest

from app.dispatch import (
    _haversine_matrix, _nearest_neighbor_route, _two_opt,
    _route_distance, optimize_dispatch, DEFAULT_CREWS,
)
from app.models import Report


class TestHaversineMatrix:
    def test_same_point_zero_distance(self):
        lats = np.array([48.7758, 48.7758])
        lngs = np.array([9.1829, 9.1829])
        d = _haversine_matrix(lats, lngs)
        assert d[0, 1] == pytest.approx(0.0, abs=1e-10)
        assert d[1, 0] == pytest.approx(0.0, abs=1e-10)

    def test_known_distance(self):
        # Stuttgart to Munich ~190 km
        lats = np.array([48.7758, 48.1351])
        lngs = np.array([9.1829, 11.5820])
        d = _haversine_matrix(lats, lngs)
        assert 185 < d[0, 1] < 195

    def test_symmetric(self):
        lats = np.array([48.78, 48.80, 48.76])
        lngs = np.array([9.18, 9.20, 9.16])
        d = _haversine_matrix(lats, lngs)
        np.testing.assert_array_almost_equal(d, d.T)

    def test_diagonal_zero(self):
        lats = np.array([52.52, 48.14, 48.78])
        lngs = np.array([13.40, 11.58, 9.18])
        d = _haversine_matrix(lats, lngs)
        np.testing.assert_array_almost_equal(np.diag(d), 0.0)


class TestNearestNeighbor:
    def test_valid_permutation(self):
        d = np.array([[0, 1, 3], [1, 0, 2], [3, 2, 0]], dtype=float)
        route = _nearest_neighbor_route(d, 0)
        assert sorted(route) == [0, 1, 2]
        assert route[0] == 0

    def test_single_node(self):
        d = np.array([[0.0]])
        route = _nearest_neighbor_route(d, 0)
        assert route == [0]

    def test_greedy_choice(self):
        # 0→1 is 1km, 0→2 is 10km, 1→2 is 2km
        d = np.array([[0, 1, 10], [1, 0, 2], [10, 2, 0]], dtype=float)
        route = _nearest_neighbor_route(d, 0)
        assert route == [0, 1, 2]


class TestTwoOpt:
    def test_no_increase(self):
        np.random.seed(42)
        n = 10
        lats = np.random.uniform(48.7, 48.8, n)
        lngs = np.random.uniform(9.1, 9.3, n)
        d = _haversine_matrix(lats, lngs)
        initial = _nearest_neighbor_route(d, 0)
        optimized = _two_opt(initial, d)
        assert _route_distance(optimized, d) <= _route_distance(initial, d) + 1e-10

    def test_short_route_unchanged(self):
        d = np.array([[0, 1], [1, 0]], dtype=float)
        route = _two_opt([0, 1], d)
        assert sorted(route) == [0, 1]

    def test_valid_permutation(self):
        np.random.seed(7)
        n = 8
        d = np.random.uniform(1, 10, (n, n))
        d = (d + d.T) / 2
        np.fill_diagonal(d, 0)
        route = list(range(n))
        optimized = _two_opt(route, d)
        assert sorted(optimized) == list(range(n))


class TestOptimizeDispatch:
    def _make_report(self, db, lat, lng, city="stuttgart", status="open"):
        r = Report(photo_path="/static/uploads/x.jpg", latitude=lat, longitude=lng,
                   city=city, category="pothole", severity="high",
                   department="roads", description="test", status=status)
        db.add(r)
        db.commit()
        db.refresh(r)
        return r

    def test_empty_city(self, db_session):
        result = optimize_dispatch("stuttgart", 3, db_session)
        assert result["total_issues"] == 0
        assert result["total_distance_km"] == 0.0
        assert result["crews"] == []

    def test_single_issue(self, db_session):
        self._make_report(db_session, 48.78, 9.18)
        result = optimize_dispatch("stuttgart", 3, db_session)
        assert result["total_issues"] == 1
        assert result["total_distance_km"] == 0.0
        assigned = [i for c in result["crews"] for i in c["route"]]
        assert len(assigned) == 1

    def test_all_issues_assigned_once(self, db_session):
        for i in range(10):
            self._make_report(db_session, 48.75 + i * 0.005, 9.15 + i * 0.005)
        result = optimize_dispatch("stuttgart", 3, db_session)
        assert result["total_issues"] == 10
        ids = [item["issue_id"] for c in result["crews"] for item in c["route"]]
        assert len(ids) == 10
        assert len(set(ids)) == 10

    def test_crews_ge_n(self, db_session):
        for i in range(3):
            self._make_report(db_session, 48.78 + i * 0.01, 9.18 + i * 0.01)
        result = optimize_dispatch("stuttgart", 10, db_session)
        assert result["total_issues"] == 3
        ids = [item["issue_id"] for c in result["crews"] for item in c["route"]]
        assert len(set(ids)) == 3

    def test_resolved_excluded(self, db_session):
        self._make_report(db_session, 48.78, 9.18, status="resolved")
        self._make_report(db_session, 48.79, 9.19, status="open")
        result = optimize_dispatch("stuttgart", 2, db_session)
        assert result["total_issues"] == 1

    def test_total_distance_equals_sum(self, db_session):
        for i in range(6):
            self._make_report(db_session, 48.75 + i * 0.01, 9.15 + i * 0.01)
        result = optimize_dispatch("stuttgart", 2, db_session)
        crew_sum = sum(c["route_distance_km"] for c in result["crews"])
        assert result["total_distance_km"] == pytest.approx(crew_sum, abs=0.01)

    def test_route_order_sequential(self, db_session):
        for i in range(5):
            self._make_report(db_session, 48.78 + i * 0.005, 9.18 + i * 0.005)
        result = optimize_dispatch("stuttgart", 2, db_session)
        for crew in result["crews"]:
            orders = [item["order"] for item in crew["route"]]
            assert orders == list(range(len(orders)))

    def test_city_filter(self, db_session):
        self._make_report(db_session, 48.78, 9.18, city="stuttgart")
        self._make_report(db_session, 52.52, 13.40, city="berlin")
        result = optimize_dispatch("stuttgart", 2, db_session)
        assert result["total_issues"] == 1
        assert result["city"] == "stuttgart"


class TestDispatchEndpoint:
    def test_valid_request(self, test_client, db_session):
        r = Report(photo_path="/static/uploads/x.jpg", latitude=48.78, longitude=9.18,
                   city="stuttgart", category="pothole", severity="high",
                   department="roads", description="test", status="open")
        db_session.add(r)
        db_session.commit()
        resp = test_client.get("/api/dispatch/optimize?city=stuttgart&crews=2")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_issues"] == 1
        assert "crews" in data

    def test_crews_zero_returns_400(self, test_client):
        resp = test_client.get("/api/dispatch/optimize?crews=0")
        assert resp.status_code == 400

    def test_crews_negative_returns_400(self, test_client):
        resp = test_client.get("/api/dispatch/optimize?crews=-1")
        assert resp.status_code == 400

    def test_empty_city(self, test_client):
        resp = test_client.get("/api/dispatch/optimize?city=stuttgart&crews=3")
        assert resp.status_code == 200
        assert resp.json()["total_issues"] == 0

    def test_default_crews(self, test_client):
        resp = test_client.get("/api/dispatch/optimize")
        assert resp.status_code == 200
        assert resp.json()["num_crews"] == 3
