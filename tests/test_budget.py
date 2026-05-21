"""Tests for LP Budget Optimizer."""

import pytest
from app.budget import optimize_budget, DEPARTMENTS, DEFAULT_BUDGET, MIN_ALLOCATION_FRACTION
from app.models import Report


def _add_reports(db, city="stuttgart", departments=None):
    """Helper to add reports for testing."""
    departments = departments or {"roads": 3, "electrical": 2, "sanitation": 1}
    for dept, count in departments.items():
        for i in range(count):
            db.add(Report(
                photo_path=f"/tmp/{dept}_{i}.jpg", latitude=48.78, longitude=9.18,
                city=city, category="pothole", severity="high",
                department=dept, description=f"Test {dept}", status="open",
            ))
    db.commit()


class TestNoReports:
    def test_equal_allocation(self, db_session):
        result = optimize_budget("stuttgart", 100000, db_session)
        for dept in DEPARTMENTS:
            assert abs(result["allocations"][dept] - 100000 / 6) < 0.01

    def test_impact_score_zero(self, db_session):
        result = optimize_budget("stuttgart", 100000, db_session)
        assert result["impact_score"] == 0

    def test_department_weights_zero(self, db_session):
        result = optimize_budget("stuttgart", 100000, db_session)
        assert all(v == 0.0 for v in result["department_weights"].values())


class TestWithReports:
    def test_allocations_sum_to_budget(self, db_session):
        _add_reports(db_session)
        result = optimize_budget("stuttgart", 100000, db_session)
        assert abs(sum(result["allocations"].values()) - 100000) < 1e-6

    def test_floor_constraint(self, db_session):
        _add_reports(db_session)
        result = optimize_budget("stuttgart", 100000, db_session)
        floor = 100000 * MIN_ALLOCATION_FRACTION
        for v in result["allocations"].values():
            assert v >= floor - 1e-6

    def test_no_negative_allocations(self, db_session):
        _add_reports(db_session)
        result = optimize_budget("stuttgart", 100000, db_session)
        assert all(v >= 0 for v in result["allocations"].values())

    def test_impact_score_range(self, db_session):
        _add_reports(db_session)
        result = optimize_budget("stuttgart", 100000, db_session)
        assert 0 < result["impact_score"] <= 1

    def test_higher_weight_gets_more(self, db_session):
        _add_reports(db_session, departments={"roads": 10, "parks": 1})
        result = optimize_budget("stuttgart", 100000, db_session)
        assert result["allocations"]["roads"] > result["allocations"]["parks"]

    def test_custom_budget(self, db_session):
        _add_reports(db_session)
        result = optimize_budget("stuttgart", 50000, db_session)
        assert abs(sum(result["allocations"].values()) - 50000) < 1e-6

    def test_response_fields(self, db_session):
        _add_reports(db_session)
        result = optimize_budget("stuttgart", 100000, db_session)
        assert result["city"] == "stuttgart"
        assert result["total_budget"] == 100000
        assert set(result["allocations"].keys()) == set(DEPARTMENTS)
        assert set(result["department_weights"].keys()) == set(DEPARTMENTS)

    def test_weights_sum_to_one(self, db_session):
        _add_reports(db_session)
        result = optimize_budget("stuttgart", 100000, db_session)
        assert abs(sum(result["department_weights"].values()) - 1.0) < 1e-6


class TestEndpoint:
    def test_default_params(self, test_client):
        resp = test_client.get("/api/budget/optimize")
        assert resp.status_code == 200
        data = resp.json()
        assert "allocations" in data
        assert data["total_budget"] == 100000

    def test_with_city(self, test_client):
        resp = test_client.get("/api/budget/optimize?city=berlin")
        assert resp.status_code == 200
        assert resp.json()["city"] == "berlin"

    def test_invalid_budget(self, test_client):
        resp = test_client.get("/api/budget/optimize?budget=-1")
        assert resp.status_code == 400

    def test_zero_budget(self, test_client):
        resp = test_client.get("/api/budget/optimize?budget=0")
        assert resp.status_code == 400

    def test_unknown_city_fallback(self, test_client):
        resp = test_client.get("/api/budget/optimize?city=unknown")
        assert resp.status_code == 200
        assert resp.json()["city"] == "stuttgart"
