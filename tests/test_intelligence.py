"""Tests for City Intelligence Score endpoint."""

import time
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

import pytest
from app.intelligence import compute_intelligence_score
from app.models import Report


def _make_report(status="open", category="pothole", severity="medium"):
    return Report(
        photo_path="x.jpg", latitude=48.783, longitude=9.18, city="stuttgart",
        category=category, severity=severity, department="roads",
        description="test", status=status,
        created_at=datetime.now(timezone.utc) - timedelta(days=1),
    )


class TestComputeIntelligenceScore:
    def test_no_reports(self, db_session):
        result = compute_intelligence_score(db_session, "stuttgart")
        assert result["city"] == "stuttgart"
        assert result["score"] == 75.0
        assert result["components"]["health"]["score"] == 100.0
        assert result["components"]["sla_compliance"]["score"] == 100.0
        assert result["components"]["transparency"]["score"] == 0.0
        assert result["components"]["anomaly_free"]["score"] == 100.0

    def test_all_resolved(self, db_session):
        for _ in range(3):
            db_session.add(_make_report(status="resolved"))
        db_session.commit()
        result = compute_intelligence_score(db_session, "stuttgart")
        assert result["components"]["sla_compliance"]["score"] == 100.0
        assert result["score"] > 0

    def test_open_reports_reduce_sla(self, db_session):
        for _ in range(5):
            db_session.add(_make_report(status="open", severity="critical"))
        db_session.commit()
        result = compute_intelligence_score(db_session, "stuttgart")
        assert result["components"]["sla_compliance"]["score"] < 100.0

    def test_active_anomaly_reduces_score(self, db_session):
        db_session.add(_make_report(status="open"))
        db_session.commit()
        fake_state = {"alpha": 5.0, "beta": 1.0, "current_count": 0,
                      "last_update": time.time(), "last_alert": time.time()}
        with patch("app.intelligence.get_state", return_value=fake_state):
            result = compute_intelligence_score(db_session, "stuttgart")
        assert result["components"]["anomaly_free"]["score"] < 100.0

    def test_invalid_city_falls_back(self, db_session):
        result = compute_intelligence_score(db_session, "nonexistent")
        assert result["city"] == "stuttgart"

    def test_score_clamped(self, db_session):
        result = compute_intelligence_score(db_session, "stuttgart")
        assert 0 <= result["score"] <= 100

    def test_response_shape(self, db_session):
        result = compute_intelligence_score(db_session, "stuttgart")
        assert "city" in result
        assert "score" in result
        assert "components" in result
        for key in ("health", "sla_compliance", "transparency", "anomaly_free"):
            assert "score" in result["components"][key]
            assert "weight" in result["components"][key]


class TestIntelligenceEndpoint:
    def test_endpoint_returns_json(self, test_client):
        resp = test_client.get("/api/intelligence-score?city=stuttgart")
        assert resp.status_code == 200
        data = resp.json()
        assert "score" in data
        assert "components" in data

    def test_endpoint_default_city(self, test_client):
        resp = test_client.get("/api/intelligence-score")
        assert resp.status_code == 200
        assert resp.json()["city"] == "stuttgart"
