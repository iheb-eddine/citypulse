"""Tests for Priority Scoring Engine."""

import time
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

import pytest
from app.priority import (
    compute_priority, compute_priorities, WEIGHTS, AGE_HALF_LIFE,
    CONFIRMATION_CAP, ANOMALY_PRIORITY_WINDOW,
)
from app.models import Report


def _make_report(**kwargs):
    defaults = {"id": 1, "photo_path": "x.jpg", "latitude": 48.781, "longitude": 9.18,
                "city": "stuttgart", "category": "pothole", "severity": "high",
                "department": "roads", "description": "test", "confirmations": 0,
                "status": "open", "created_at": datetime(2026, 5, 1, tzinfo=timezone.utc)}
    defaults.update(kwargs)
    r = Report(**defaults)
    return r


class TestSeverityFactor:
    def test_critical(self):
        r = _make_report(severity="critical")
        result = compute_priority(r, "stuttgart", datetime(2026, 5, 1, tzinfo=timezone.utc))
        assert result["factors"]["severity"] == 1.0

    def test_low(self):
        r = _make_report(severity="low")
        result = compute_priority(r, "stuttgart", datetime(2026, 5, 1, tzinfo=timezone.utc))
        assert result["factors"]["severity"] == pytest.approx(0.2)

    def test_medium(self):
        r = _make_report(severity="medium")
        result = compute_priority(r, "stuttgart", datetime(2026, 5, 1, tzinfo=timezone.utc))
        assert result["factors"]["severity"] == pytest.approx(0.4)


class TestAgeFactor:
    def test_brand_new(self):
        now = datetime(2026, 5, 1, tzinfo=timezone.utc)
        r = _make_report(created_at=now)
        result = compute_priority(r, "stuttgart", now)
        assert result["factors"]["age"] == pytest.approx(0.0, abs=1e-9)

    def test_seven_days(self):
        now = datetime(2026, 5, 8, tzinfo=timezone.utc)
        r = _make_report(created_at=datetime(2026, 5, 1, tzinfo=timezone.utc))
        result = compute_priority(r, "stuttgart", now)
        assert result["factors"]["age"] == pytest.approx(0.6321, abs=0.01)

    def test_capped_at_one(self):
        now = datetime(2026, 8, 1, tzinfo=timezone.utc)
        r = _make_report(created_at=datetime(2026, 5, 1, tzinfo=timezone.utc))
        result = compute_priority(r, "stuttgart", now)
        assert result["factors"]["age"] == pytest.approx(1.0, abs=1e-4)


class TestConfirmationFactor:
    def test_zero_confirmations(self):
        r = _make_report(confirmations=0)
        result = compute_priority(r, "stuttgart", datetime(2026, 5, 1, tzinfo=timezone.utc))
        assert result["factors"]["confirmations"] == 0.0

    def test_cap_confirmations(self):
        r = _make_report(confirmations=10)
        result = compute_priority(r, "stuttgart", datetime(2026, 5, 1, tzinfo=timezone.utc))
        assert result["factors"]["confirmations"] == pytest.approx(1.0, abs=1e-9)

    def test_one_confirmation(self):
        r = _make_report(confirmations=1)
        result = compute_priority(r, "stuttgart", datetime(2026, 5, 1, tzinfo=timezone.utc))
        assert result["factors"]["confirmations"] == pytest.approx(0.289, abs=0.01)


class TestAnomalyFactor:
    def test_no_state(self):
        r = _make_report()
        with patch("app.priority.anomaly.get_state", return_value=None):
            result = compute_priority(r, "stuttgart", datetime(2026, 5, 1, tzinfo=timezone.utc))
        assert result["factors"]["anomaly"] == 0.0

    def test_recent_alert(self):
        r = _make_report()
        with patch("app.priority.anomaly.get_state", return_value={"last_alert": time.time() - 100}):
            result = compute_priority(r, "stuttgart", datetime(2026, 5, 1, tzinfo=timezone.utc))
        assert result["factors"]["anomaly"] == 1.0

    def test_old_alert(self):
        r = _make_report()
        with patch("app.priority.anomaly.get_state", return_value={"last_alert": time.time() - 7200}):
            result = compute_priority(r, "stuttgart", datetime(2026, 5, 1, tzinfo=timezone.utc))
        assert result["factors"]["anomaly"] == 0.0


class TestSlaRisk:
    def test_brand_new_low_risk(self):
        now = datetime(2026, 5, 1, tzinfo=timezone.utc)
        r = _make_report(created_at=now)
        result = compute_priority(r, "stuttgart", now)
        assert result["factors"]["sla_risk"] == pytest.approx(0.0, abs=0.01)

    def test_old_critical_high_risk(self):
        now = datetime(2026, 5, 4, tzinfo=timezone.utc)
        r = _make_report(created_at=datetime(2026, 5, 1, tzinfo=timezone.utc), severity="critical")
        result = compute_priority(r, "stuttgart", now)
        assert result["factors"]["sla_risk"] > 0.9


class TestScoreBounds:
    def test_score_between_0_and_100(self):
        r = _make_report(confirmations=5)
        now = datetime(2026, 5, 5, tzinfo=timezone.utc)
        result = compute_priority(r, "stuttgart", now)
        assert 0 <= result["score"] <= 100

    def test_weights_in_result(self):
        r = _make_report()
        result = compute_priority(r, "stuttgart", datetime(2026, 5, 1, tzinfo=timezone.utc))
        assert result["weights"] == WEIGHTS


class TestComputePriorities:
    def test_sorted_descending(self):
        r1 = _make_report(id=1, severity="low", confirmations=0)
        r2 = _make_report(id=2, severity="critical", confirmations=10,
                          created_at=datetime(2026, 4, 1, tzinfo=timezone.utc))
        results = compute_priorities([r1, r2], "stuttgart")
        assert results[0]["report_id"] == 2
        assert results[0]["score"] >= results[1]["score"]


class TestEndpoints:
    def test_priority_list(self, test_client, db_session):
        r = Report(photo_path="x.jpg", latitude=48.781, longitude=9.18, city="stuttgart",
                   category="pothole", severity="high", department="roads",
                   description="test", confirmations=3, status="open",
                   created_at=datetime(2026, 5, 1))
        db_session.add(r)
        db_session.commit()
        resp = test_client.get("/api/reports/priority?city=stuttgart")
        assert resp.status_code == 200
        data = resp.json()
        assert data["city"] == "stuttgart"
        assert data["total"] == 1
        assert "score" in data["reports"][0]

    def test_priority_single(self, test_client, db_session):
        r = Report(photo_path="x.jpg", latitude=48.781, longitude=9.18, city="stuttgart",
                   category="pothole", severity="high", department="roads",
                   description="test", confirmations=0, status="open",
                   created_at=datetime(2026, 5, 1))
        db_session.add(r)
        db_session.commit()
        resp = test_client.get(f"/api/reports/{r.id}/priority")
        assert resp.status_code == 200
        data = resp.json()
        assert data["report_id"] == r.id
        assert "factors" in data

    def test_priority_not_found(self, test_client):
        resp = test_client.get("/api/reports/9999/priority")
        assert resp.status_code == 404

    def test_resolved_excluded(self, test_client, db_session):
        r = Report(photo_path="x.jpg", latitude=48.781, longitude=9.18, city="stuttgart",
                   category="pothole", severity="high", department="roads",
                   description="test", confirmations=0, status="resolved",
                   created_at=datetime(2026, 5, 1))
        db_session.add(r)
        db_session.commit()
        resp = test_client.get("/api/reports/priority?city=stuttgart")
        assert resp.json()["total"] == 0


class TestEdgeCases:
    def test_negative_age_hours_no_crash(self):
        """Bug fix: now < created_at (clock skew) must not crash or go negative."""
        now = datetime(2026, 5, 1, tzinfo=timezone.utc)
        r = _make_report(created_at=datetime(2026, 5, 2, tzinfo=timezone.utc))
        result = compute_priority(r, "stuttgart", now)
        assert result["factors"]["age"] == 0.0
        assert result["factors"]["sla_risk"] == pytest.approx(0.0, abs=0.01)
        assert 0 <= result["score"] <= 100

    def test_negative_confirmations_no_crash(self):
        """Bug fix: negative confirmations must not raise math domain error."""
        r = _make_report(confirmations=-1)
        result = compute_priority(r, "stuttgart", datetime(2026, 5, 1, tzinfo=timezone.utc))
        assert result["factors"]["confirmations"] == 0.0

    def test_score_clamped_to_bounds(self):
        """Defense-in-depth: score always in [0, 100]."""
        r = _make_report(severity="critical", confirmations=100,
                         created_at=datetime(2025, 1, 1, tzinfo=timezone.utc))
        with patch("app.priority.anomaly.get_state", return_value={"last_alert": time.time()}):
            result = compute_priority(r, "stuttgart", datetime(2026, 5, 22, tzinfo=timezone.utc))
        assert 0 <= result["score"] <= 100
