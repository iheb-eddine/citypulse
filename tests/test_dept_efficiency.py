"""Tests for GET /api/departments/efficiency endpoint."""
from datetime import datetime, timedelta
from app.models import Report


def _add(db, dept, status="open", hours_ago=48, city="stuttgart"):
    r = Report(photo_path="x.jpg", latitude=48.78, longitude=9.18, city=city,
               category="pothole", severity="high", department=dept,
               description="t", status=status, created_at=datetime.utcnow() - timedelta(hours=hours_ago))
    db.add(r)
    db.commit()


def test_efficiency_ranking_order(test_client, db_session):
    # roads: 2 resolved, 1 open (high resolution rate)
    _add(db_session, "roads", status="resolved")
    _add(db_session, "roads", status="resolved")
    _add(db_session, "roads", status="open", hours_ago=24)
    # sanitation: 1 resolved, 2 open (low resolution rate, high age)
    _add(db_session, "sanitation", status="resolved")
    _add(db_session, "sanitation", status="open", hours_ago=100)
    _add(db_session, "sanitation", status="open", hours_ago=200)

    resp = test_client.get("/api/departments/efficiency", params={"city": "stuttgart"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["city"] == "stuttgart"
    assert len(data["departments"]) == 2
    assert data["departments"][0]["name"] == "roads"
    assert data["departments"][0]["rank"] == 1
    assert data["departments"][1]["name"] == "sanitation"
    assert data["departments"][1]["rank"] == 2
    assert data["departments"][0]["efficiency_score"] > data["departments"][1]["efficiency_score"]


def test_efficiency_no_reports(test_client, db_session):
    resp = test_client.get("/api/departments/efficiency", params={"city": "stuttgart"})
    assert resp.status_code == 200
    assert resp.json() == {"city": "stuttgart", "departments": []}


def test_efficiency_all_resolved(test_client, db_session):
    _add(db_session, "roads", status="resolved")
    _add(db_session, "electrical", status="resolved")
    resp = test_client.get("/api/departments/efficiency", params={"city": "stuttgart"})
    data = resp.json()
    for dept in data["departments"]:
        assert dept["resolution_rate"] == 1.0
        assert dept["avg_age_hours"] == 0.0
        assert dept["efficiency_score"] == 1.0


def test_efficiency_single_department(test_client, db_session):
    _add(db_session, "water", status="open", hours_ago=50)
    resp = test_client.get("/api/departments/efficiency", params={"city": "stuttgart"})
    data = resp.json()
    assert len(data["departments"]) == 1
    assert data["departments"][0]["rank"] == 1
    assert data["departments"][0]["name"] == "water"
    assert data["departments"][0]["workload_share"] == 1.0
