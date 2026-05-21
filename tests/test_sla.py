"""Tests for SLA Survival Prediction (Weibull analysis)."""

import math
import pytest
from app.sla import get_params, survival, percentile, WEIBULL_PARAMS, _DEFAULT, SLA_TARGET_HOURS
from app.models import Report


class TestWeibullMath:
    def test_survival_at_zero(self):
        assert survival(0, 100, 1.5) == 1.0

    def test_survival_decreases(self):
        assert survival(50, 100, 1.5) > survival(100, 100, 1.5)

    def test_survival_approaches_zero(self):
        assert survival(10000, 100, 1.5) < 0.001

    def test_percentile_median(self):
        scale, shape = 96, 1.5
        med = percentile(0.5, scale, shape)
        expected = scale * (math.log(2) ** (1 / shape))
        assert abs(med - expected) < 1e-10

    def test_percentile_ordering(self):
        scale, shape = 72, 1.4
        assert percentile(0.5, scale, shape) < percentile(0.75, scale, shape) < percentile(0.9, scale, shape)

    def test_survival_at_median_is_half(self):
        scale, shape = 120, 1.5
        med = percentile(0.5, scale, shape)
        assert abs(survival(med, scale, shape) - 0.5) < 1e-10


class TestGetParams:
    def test_known_category(self):
        assert get_params("pothole", "high") == (72, 1.7)

    def test_unknown_category_uses_default(self):
        assert get_params("unknown_cat", "low") == _DEFAULT["low"]

    def test_unknown_severity_uses_medium_default(self):
        assert get_params("pothole", "unknown_sev") == _DEFAULT["medium"]

    def test_pothole_slower_than_graffiti(self):
        for sev in ("low", "medium", "high", "critical"):
            pot_scale, _ = get_params("pothole", sev)
            graf_scale, _ = get_params("graffiti", sev)
            assert pot_scale > graf_scale


class TestReportSlaEndpoint:
    def test_report_sla(self, test_client, db_session):
        r = Report(photo_path="x.jpg", latitude=48.78, longitude=9.18, city="stuttgart",
                   category="pothole", severity="high", department="roads", description="test")
        db_session.add(r)
        db_session.commit()
        resp = test_client.get(f"/api/reports/{r.id}/sla")
        assert resp.status_code == 200
        data = resp.json()
        assert data["category"] == "pothole"
        assert data["severity"] == "high"
        assert data["scale"] == 72
        assert data["shape"] == 1.7
        assert len(data["survival_curve"]) == 10
        assert data["survival_curve"][0]["survival"] == 1.0
        assert data["median_hours"] > 0
        assert data["p75_hours"] > data["median_hours"]
        assert data["p90_hours"] > data["p75_hours"]

    def test_report_not_found(self, test_client):
        resp = test_client.get("/api/reports/99999/sla")
        assert resp.status_code == 404


class TestSlaSummaryEndpoint:
    def test_empty_city(self, test_client):
        resp = test_client.get("/api/sla/summary?city=stuttgart")
        assert resp.status_code == 200
        data = resp.json()
        assert data["open_reports"] == 0
        assert data["overall_compliance"] == 1.0
        assert data["compliance_rate"] == 1.0
        assert data["total_open"] == 0
        assert data["on_track"] == 0
        assert data["at_risk"] == 0
        assert data["overdue"] == 0

    def test_with_reports(self, test_client, db_session):
        for cat in ("pothole", "graffiti"):
            db_session.add(Report(photo_path="x.jpg", latitude=48.78, longitude=9.18,
                                  city="stuttgart", category=cat, severity="medium",
                                  department="roads", description="t"))
        db_session.commit()
        resp = test_client.get("/api/sla/summary?city=stuttgart")
        data = resp.json()
        assert data["open_reports"] == 2
        assert 0 < data["overall_compliance"] < 1
        assert "pothole" in data["by_category"]
        assert "graffiti" in data["by_category"]
        # Graffiti should have higher compliance (faster resolution)
        assert data["by_category"]["graffiti"] > data["by_category"]["pothole"]
        # New fields
        assert data["compliance_rate"] == data["overall_compliance"]
        assert data["total_open"] == 2
        assert data["on_track"] + data["at_risk"] + data["overdue"] == 2
