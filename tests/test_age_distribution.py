"""Tests for GET /api/reports/age-distribution endpoint."""
from datetime import datetime, timedelta
from app.models import Report


def _add(db, hours_ago, status="open", city="stuttgart"):
    r = Report(photo_path="x.jpg", latitude=48.78, longitude=9.18, city=city,
               category="pothole", severity="high", department="roads",
               description="t", status=status, created_at=datetime.utcnow() - timedelta(hours=hours_ago))
    db.add(r)
    db.commit()


def test_age_distribution_multiple_buckets(test_client, db_session):
    _add(db_session, 5)     # 0-24h
    _add(db_session, 50)    # 1-3d
    _add(db_session, 100)   # 3-7d
    _add(db_session, 200)   # 7-14d
    _add(db_session, 500)   # 14-30d
    _add(db_session, 800)   # 30d+
    resp = test_client.get("/api/reports/age-distribution", params={"city": "stuttgart"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["city"] == "stuttgart"
    assert data["total_open"] == 6
    assert len(data["buckets"]) == 6
    counts = [b["count"] for b in data["buckets"]]
    assert counts == [1, 1, 1, 1, 1, 1]
    assert all(abs(b["percentage"] - 16.7) < 0.1 for b in data["buckets"])


def test_age_distribution_empty(test_client, db_session):
    resp = test_client.get("/api/reports/age-distribution", params={"city": "stuttgart"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_open"] == 0
    assert data["median_age_hours"] == 0
    assert data["oldest_report_hours"] == 0
    assert all(b["count"] == 0 for b in data["buckets"])


def test_age_distribution_excludes_resolved(test_client, db_session):
    _add(db_session, 10, status="resolved")
    _add(db_session, 20, status="open")
    _add(db_session, 30, status="in_progress")
    resp = test_client.get("/api/reports/age-distribution", params={"city": "stuttgart"})
    data = resp.json()
    assert data["total_open"] == 2


def test_age_distribution_median(test_client, db_session):
    _add(db_session, 10)
    _add(db_session, 20)
    _add(db_session, 30)
    _add(db_session, 40)
    resp = test_client.get("/api/reports/age-distribution", params={"city": "stuttgart"})
    data = resp.json()
    # Even count: median = avg of 2nd and 3rd values (sorted: ~10,20,30,40 → avg(20,30)=25)
    assert 20 <= data["median_age_hours"] <= 30


def test_age_distribution_default_city(test_client, db_session):
    _add(db_session, 12)
    resp = test_client.get("/api/reports/age-distribution")
    assert resp.status_code == 200
    assert resp.json()["total_open"] == 1
