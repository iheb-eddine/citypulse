"""Tests for the Time-Lapse Simulation endpoint."""

from datetime import datetime, timedelta

from app.models import Report


def _add_report(db, city="stuttgart", category="pothole", severity="high", days_ago=0):
    r = Report(
        photo_path="test.jpg", latitude=48.77, longitude=9.18,
        city=city, category=category, severity=severity,
        department="roads", description="test",
        created_at=datetime.now() - timedelta(days=days_ago),
    )
    db.add(r)
    db.commit()
    return r


def test_timelapse_empty(test_client, db_session):
    resp = test_client.get("/api/timelapse?city=stuttgart&days=5")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 5
    assert all(s["report_count"] == 0 for s in data)
    assert all(s["health_score"] == 100 for s in data)


def test_timelapse_with_reports(test_client, db_session):
    _add_report(db_session, days_ago=2)
    _add_report(db_session, days_ago=1, category="graffiti", severity="low")
    _add_report(db_session, days_ago=0, category="flooding", severity="medium")

    resp = test_client.get("/api/timelapse?city=stuttgart&days=5")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 5
    # Reports accumulate over time
    counts = [s["report_count"] for s in data]
    assert counts == sorted(counts)  # non-decreasing
    # Last day should have all 3
    assert data[-1]["report_count"] == 3
    assert data[-1]["health_score"] < 100


def test_timelapse_new_reports_today(test_client, db_session):
    _add_report(db_session, days_ago=0)
    _add_report(db_session, days_ago=0)
    _add_report(db_session, days_ago=1)

    resp = test_client.get("/api/timelapse?city=stuttgart&days=3")
    data = resp.json()
    assert data[-1]["new_reports_today"] == 2
    assert data[-2]["new_reports_today"] == 1


def test_timelapse_categories_and_severity(test_client, db_session):
    _add_report(db_session, category="pothole", severity="high", days_ago=0)
    _add_report(db_session, category="pothole", severity="low", days_ago=0)

    resp = test_client.get("/api/timelapse?city=stuttgart&days=1")
    data = resp.json()
    assert data[0]["categories"] == {"pothole": 2}
    assert data[0]["severity_distribution"] == {"high": 1, "low": 1}


def test_timelapse_days_clamped(test_client, db_session):
    resp = test_client.get("/api/timelapse?city=stuttgart&days=0")
    assert resp.status_code == 200
    assert len(resp.json()) == 1  # clamped to 1

    resp = test_client.get("/api/timelapse?city=stuttgart&days=999")
    assert resp.status_code == 200
    assert len(resp.json()) == 365  # clamped to 365


def test_timelapse_default_days(test_client, db_session):
    resp = test_client.get("/api/timelapse?city=stuttgart")
    assert resp.status_code == 200
    assert len(resp.json()) == 30


def test_timelapse_snapshot_structure(test_client, db_session):
    _add_report(db_session, days_ago=0)
    resp = test_client.get("/api/timelapse?city=stuttgart&days=1")
    data = resp.json()
    snapshot = data[0]
    assert set(snapshot.keys()) == {
        "day", "date", "report_count", "health_score",
        "categories", "severity_distribution", "new_reports_today",
    }
    assert snapshot["day"] == 1
    assert isinstance(snapshot["date"], str)
