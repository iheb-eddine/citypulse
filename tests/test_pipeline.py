"""Tests for Pipeline Visualizer endpoints."""

from datetime import datetime
from app.models import Report


def _create_report(db, **overrides):
    defaults = dict(
        photo_path="/static/uploads/test.jpg", latitude=48.77, longitude=9.18,
        city="stuttgart", category="pothole", severity="high", department="roads",
        description="Test", status="open", created_at=datetime(2026, 5, 22, 13, 0, 0),
    )
    defaults.update(overrides)
    r = Report(**defaults)
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


def test_pipeline_happy_path(test_client, db_session):
    r = _create_report(db_session)
    resp = test_client.get(f"/api/reports/{r.id}/pipeline")
    assert resp.status_code == 200
    data = resp.json()
    assert data["report_id"] == r.id
    assert len(data["stages"]) == 5
    assert all(s["status"] == "completed" for s in data["stages"])
    assert data["stages"][0]["details"]["photo_path"] == "/static/uploads/test.jpg"
    assert data["stages"][1]["details"]["category"] == "pothole"
    assert data["stages"][4]["details"]["eligible"] is True


def test_pipeline_not_found(test_client):
    resp = test_client.get("/api/reports/9999/pipeline")
    assert resp.status_code == 404
    assert resp.json() == {"error": "Report not found"}


def test_pipeline_classification_skipped(test_client, db_session):
    _create_report(db_session, category="unclassified")
    resp = test_client.get("/api/reports/1/pipeline")
    stages = resp.json()["stages"]
    assert stages[1]["status"] == "skipped"


def test_pipeline_dispatch_skipped_resolved(test_client, db_session):
    _create_report(db_session, status="resolved")
    resp = test_client.get("/api/reports/1/pipeline")
    stages = resp.json()["stages"]
    assert stages[4]["status"] == "skipped"
    assert stages[4]["details"]["eligible"] is False


def test_pipeline_dispatch_in_progress(test_client, db_session):
    _create_report(db_session, status="in_progress")
    resp = test_client.get("/api/reports/1/pipeline")
    stages = resp.json()["stages"]
    assert stages[4]["status"] == "completed"
    assert stages[4]["details"]["eligible"] is False


def test_pipeline_stages_endpoint(test_client):
    resp = test_client.get("/api/pipeline/stages")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["stages"]) == 5
    names = [s["name"] for s in data["stages"]]
    assert names == ["upload", "classification", "anomaly_check", "budget_impact", "dispatch_eligible"]
    assert all("description" in s for s in data["stages"])
