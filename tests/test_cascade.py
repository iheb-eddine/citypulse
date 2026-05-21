"""Tests for the Full Cascade Endpoint."""

from datetime import datetime
from app.models import Report


def _create_report(db, **overrides):
    defaults = dict(
        photo_path="/static/uploads/test.jpg", latitude=48.77, longitude=9.18,
        city="stuttgart", category="pothole", severity="high", department="roads",
        description="Test pothole", status="open", created_at=datetime(2026, 5, 22, 13, 0, 0),
    )
    defaults.update(overrides)
    r = Report(**defaults)
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


def test_cascade_happy_path(test_client, db_session):
    r = _create_report(db_session)
    resp = test_client.get(f"/api/reports/{r.id}/cascade")
    assert resp.status_code == 200
    data = resp.json()
    assert data["report"]["id"] == r.id
    assert data["report"]["category"] == "pothole"
    assert data["report"]["severity"] == "high"
    assert data["report"]["department"] == "roads"
    assert data["report"]["status"] == "open"
    assert "created_at" in data["report"]
    assert len(data["pipeline"]) == 5
    assert data["reasoning"]["severity"] == "high"
    assert "score" in data["priority"]
    assert "median_hours" in data["sla"]
    assert isinstance(data["duplicates"], list)


def test_cascade_not_found(test_client):
    resp = test_client.get("/api/reports/9999/cascade")
    assert resp.status_code == 404
    assert resp.json() == {"error": "Report not found"}


def test_cascade_sla_values(test_client, db_session):
    r = _create_report(db_session, category="streetlight", severity="critical")
    resp = test_client.get(f"/api/reports/{r.id}/cascade")
    data = resp.json()
    assert data["sla"]["scale"] == 18
    assert data["sla"]["shape"] == 2.2
    assert data["sla"]["median_hours"] > 0
    assert data["sla"]["p75_hours"] > data["sla"]["median_hours"]
    assert data["sla"]["p90_hours"] > data["sla"]["p75_hours"]


def test_cascade_reasoning_steps(test_client, db_session):
    r = _create_report(db_session, description="danger hazard emergency")
    resp = test_client.get(f"/api/reports/{r.id}/cascade")
    data = resp.json()
    assert len(data["reasoning"]["reasoning_steps"]) == 5
    assert "conclusion" in data["reasoning"]
