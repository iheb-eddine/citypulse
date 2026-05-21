"""Tests for Transparency Dashboard — SLA compliance with exponential decay."""

import math
from datetime import datetime, timezone, timedelta

import pytest
from app.transparency import compute_transparency, _grade, DECAY_RATE
from app.models import Report


def _make_report(department="roads", category="pothole", severity="medium",
                 status="resolved", age_days=0):
    now = datetime.now(timezone.utc)
    r = Report(
        photo_path="x.jpg", latitude=48.7, longitude=9.1, city="stuttgart",
        category=category, severity=severity, department=department,
        description="test", status=status,
        created_at=now - timedelta(days=age_days),
    )
    return r


class TestGrade:
    def test_grade_a(self):
        assert _grade(95) == "A"

    def test_grade_b(self):
        assert _grade(85) == "B"

    def test_grade_c(self):
        assert _grade(75) == "C"

    def test_grade_d(self):
        assert _grade(65) == "D"

    def test_grade_f(self):
        assert _grade(50) == "F"

    def test_grade_boundary(self):
        assert _grade(90) == "A"
        assert _grade(89.9) == "B"


class TestComputeTransparency:
    def test_all_resolved_score_100(self):
        reports = [_make_report(status="resolved", age_days=i) for i in range(5)]
        depts, overall = compute_transparency(reports)
        assert overall == 100.0
        assert depts[0]["score"] == 100.0
        assert depts[0]["grade"] == "A"

    def test_all_overdue_open_score_0(self):
        reports = [_make_report(status="open", age_days=10) for _ in range(3)]
        depts, overall = compute_transparency(reports)
        assert overall == 0.0
        assert depts[0]["grade"] == "F"

    def test_recent_open_within_sla_compliant(self):
        # age=1 day = 24 hours < 48 SLA target -> compliant
        reports = [_make_report(status="open", age_days=1)]
        depts, overall = compute_transparency(reports)
        assert overall == 100.0

    def test_decay_weighting(self):
        # Recent non-compliant weighs more than old compliant
        now = datetime.now(timezone.utc)
        reports = [
            _make_report(status="open", age_days=3),   # 72h > 48 SLA -> non-compliant, weight=exp(-0.15)
            _make_report(status="resolved", age_days=30),  # compliant, weight=exp(-1.5)
        ]
        depts, overall = compute_transparency(reports, now=now)
        # Non-compliant has higher weight, so overall < 50
        w_new = math.exp(-DECAY_RATE * 3)
        w_old = math.exp(-DECAY_RATE * 30)
        expected = (0 * w_new + 1 * w_old) / (w_new + w_old) * 100
        assert abs(overall - expected) < 0.1

    def test_multiple_departments(self):
        reports = [
            _make_report(department="roads", status="resolved"),
            _make_report(department="water", status="open", age_days=5),
        ]
        depts, overall = compute_transparency(reports)
        names = [d["name"] for d in depts]
        assert "roads" in names
        assert "water" in names
        roads = next(d for d in depts if d["name"] == "roads")
        assert roads["score"] == 100.0
        water = next(d for d in depts if d["name"] == "water")
        assert water["score"] == 0.0

    def test_resolved_count(self):
        reports = [
            _make_report(status="resolved"),
            _make_report(status="open", age_days=0),
        ]
        depts, _ = compute_transparency(reports)
        assert depts[0]["resolved_count"] + depts[0]["total_reports"] - depts[0]["resolved_count"] == depts[0]["total_reports"]

    def test_avg_resolution_hours_positive(self):
        reports = [_make_report()]
        depts, _ = compute_transparency(reports)
        assert depts[0]["avg_resolution_hours"] > 0

    def test_sorted_by_score_desc(self):
        reports = [
            _make_report(department="roads", status="open", age_days=5),
            _make_report(department="water", status="resolved"),
        ]
        depts, _ = compute_transparency(reports)
        assert depts[0]["score"] >= depts[1]["score"]


class TestEndpoint:
    def test_transparency_empty_city(self, test_client):
        resp = test_client.get("/api/transparency?city=nonexistent")
        assert resp.status_code == 200
        data = resp.json()
        assert data["overall_score"] == 0
        assert data["departments"] == []

    def test_transparency_with_data(self, test_client, db_session):
        now = datetime.now(timezone.utc)
        db_session.add(Report(
            photo_path="x.jpg", latitude=48.7, longitude=9.1, city="testcity",
            category="pothole", severity="medium", department="roads",
            description="test", status="resolved", created_at=now,
        ))
        db_session.commit()
        resp = test_client.get("/api/transparency?city=testcity")
        assert resp.status_code == 200
        data = resp.json()
        assert data["city"] == "testcity"
        assert data["overall_score"] == 100.0
        assert len(data["departments"]) == 1
        dept = data["departments"][0]
        assert dept["name"] == "roads"
        assert dept["total_reports"] == 1
        assert dept["resolved_count"] == 1
        assert "grade" in dept
