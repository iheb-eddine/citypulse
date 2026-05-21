"""Tests for GET /api/neighborhoods/compare endpoint."""
from datetime import datetime
from app.models import Report


def _add_report(db, lat, lng, category="pothole", severity="high", status="open", city="stuttgart"):
    r = Report(photo_path="x.jpg", latitude=lat, longitude=lng, city=city,
               category=category, severity=severity, department="roads",
               description="test", status=status, created_at=datetime.now())
    db.add(r)
    db.commit()
    return r


def test_compare_happy_path(test_client, db_session):
    # Hauptbahnhof bbox: (48.781, 48.788, 9.177, 9.186)
    _add_report(db_session, 48.784, 9.180, category="pothole", severity="high", status="resolved")
    _add_report(db_session, 48.785, 9.181, category="pothole", severity="low", status="open")
    # Bad Cannstatt bbox: (48.800, 48.809, 9.209, 9.219)
    _add_report(db_session, 48.804, 9.213, category="graffiti", severity="medium", status="open")

    resp = test_client.get("/api/neighborhoods/compare", params={"a": "Hauptbahnhof", "b": "Bad Cannstatt", "city": "stuttgart"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["city"] == "stuttgart"
    assert len(data["neighborhoods"]) == 2
    hbf = data["neighborhoods"][0]
    assert hbf["name"] == "Hauptbahnhof"
    assert hbf["report_count"] == 2
    assert hbf["top_category"] == "pothole"
    assert hbf["resolution_rate"] == 0.5
    bc = data["neighborhoods"][1]
    assert bc["name"] == "Bad Cannstatt"
    assert bc["report_count"] == 1
    assert bc["top_category"] == "graffiti"


def test_compare_unknown_neighborhood(test_client):
    resp = test_client.get("/api/neighborhoods/compare", params={"a": "Hauptbahnhof", "b": "Narnia", "city": "stuttgart"})
    assert resp.status_code == 422
    assert "Narnia" in resp.json()["error"]


def test_compare_missing_params(test_client):
    resp = test_client.get("/api/neighborhoods/compare", params={"a": "Hauptbahnhof"})
    assert resp.status_code == 422


def test_compare_empty_neighborhood(test_client, db_session):
    resp = test_client.get("/api/neighborhoods/compare", params={"a": "Hauptbahnhof", "b": "Bad Cannstatt", "city": "stuttgart"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["neighborhoods"][0]["report_count"] == 0
    assert data["neighborhoods"][0]["health_score"] == 100
    assert data["neighborhoods"][0]["top_category"] is None
    assert data["neighborhoods"][0]["anomaly_active"] is False


def test_compare_anomaly_active_false_by_default(test_client, db_session):
    _add_report(db_session, 48.784, 9.180)
    resp = test_client.get("/api/neighborhoods/compare", params={"a": "Hauptbahnhof", "b": "Bad Cannstatt"})
    assert resp.status_code == 200
    assert resp.json()["neighborhoods"][0]["anomaly_active"] is False
