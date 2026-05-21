"""Tests for the City Health History endpoint."""

from datetime import datetime, timedelta

from app.models import Report


def _add_report(db, lat=48.783, lng=9.180, category="pothole", severity="high", days_ago=0):
    """Add a report in Hauptbahnhof neighborhood (48.781-48.788, 9.177-9.186)."""
    r = Report(
        photo_path="test.jpg", latitude=lat, longitude=lng,
        city="stuttgart", category=category, severity=severity,
        department="roads", description="test",
        created_at=datetime.now() - timedelta(days=days_ago),
    )
    db.add(r)
    db.commit()
    return r


def test_health_history_empty(test_client, db_session):
    resp = test_client.get("/api/health/history?city=stuttgart&days=5")
    assert resp.status_code == 200
    data = resp.json()
    assert data["city"] == "stuttgart"
    assert data["days"] == 5
    assert data["neighborhoods"] == []


def test_health_history_with_reports(test_client, db_session):
    _add_report(db_session, days_ago=2)
    _add_report(db_session, days_ago=0, category="graffiti", severity="low")

    resp = test_client.get("/api/health/history?city=stuttgart&days=5")
    data = resp.json()
    assert len(data["neighborhoods"]) == 1
    nh = data["neighborhoods"][0]
    assert nh["name"] == "Hauptbahnhof"
    assert len(nh["history"]) == 5
    # Last day should have cumulative health_score < 100
    assert nh["history"][-1]["health_score"] < 100


def test_health_history_days_clamped(test_client, db_session):
    resp = test_client.get("/api/health/history?city=stuttgart&days=0")
    assert resp.status_code == 200
    assert resp.json()["days"] == 1

    resp = test_client.get("/api/health/history?city=stuttgart&days=999")
    assert resp.status_code == 200
    assert resp.json()["days"] == 365


def test_health_history_neighborhood_filter(test_client, db_session):
    _add_report(db_session, days_ago=0)  # Hauptbahnhof
    # Add report in Stuttgart-West (48.767-48.775, 9.164-9.176)
    _add_report(db_session, lat=48.770, lng=9.170, days_ago=0)

    resp = test_client.get("/api/health/history?city=stuttgart&days=3&neighborhood=Hauptbahnhof")
    data = resp.json()
    assert len(data["neighborhoods"]) == 1
    assert data["neighborhoods"][0]["name"] == "Hauptbahnhof"


def test_health_history_invalid_neighborhood_filter(test_client, db_session):
    _add_report(db_session, days_ago=0)
    resp = test_client.get("/api/health/history?city=stuttgart&days=3&neighborhood=Nonexistent")
    data = resp.json()
    assert data["neighborhoods"] == []


def test_health_history_cumulative_score(test_client, db_session):
    _add_report(db_session, days_ago=2, severity="critical")

    resp = test_client.get("/api/health/history?city=stuttgart&days=3")
    data = resp.json()
    nh = data["neighborhoods"][0]
    # Day with the report and all subsequent days should have same cumulative score
    scores = [h["health_score"] for h in nh["history"]]
    # Once a report exists, score stays the same for remaining days (cumulative)
    assert scores[-1] == scores[-2]  # last two days same (report was 2 days ago)


def test_health_history_daily_report_count(test_client, db_session):
    _add_report(db_session, days_ago=0)
    _add_report(db_session, days_ago=0)
    _add_report(db_session, days_ago=1)

    resp = test_client.get("/api/health/history?city=stuttgart&days=3")
    data = resp.json()
    nh = data["neighborhoods"][0]
    assert nh["history"][-1]["report_count"] == 2
    assert nh["history"][-2]["report_count"] == 1


def test_health_history_top_category(test_client, db_session):
    _add_report(db_session, days_ago=0, category="pothole")
    _add_report(db_session, days_ago=0, category="pothole")
    _add_report(db_session, days_ago=0, category="graffiti")

    resp = test_client.get("/api/health/history?city=stuttgart&days=1")
    data = resp.json()
    assert data["neighborhoods"][0]["history"][0]["top_category"] == "pothole"


def test_health_history_no_reports_day(test_client, db_session):
    _add_report(db_session, days_ago=2)

    resp = test_client.get("/api/health/history?city=stuttgart&days=3")
    data = resp.json()
    nh = data["neighborhoods"][0]
    # Days after the report: report_count=0, top_category=None, but health_score < 100
    assert nh["history"][-1]["report_count"] == 0
    assert nh["history"][-1]["top_category"] is None
    assert nh["history"][-1]["health_score"] < 100


def test_health_history_excludes_non_neighborhood(test_client, db_session):
    # Report outside all neighborhoods but inside city bbox (maps to city name)
    _add_report(db_session, lat=48.82, lng=9.25, days_ago=0)
    resp = test_client.get("/api/health/history?city=stuttgart&days=3")
    data = resp.json()
    assert data["neighborhoods"] == []


def test_health_history_response_structure(test_client, db_session):
    _add_report(db_session, days_ago=0)
    resp = test_client.get("/api/health/history?city=stuttgart&days=1")
    data = resp.json()
    assert set(data.keys()) == {"city", "days", "neighborhoods"}
    nh = data["neighborhoods"][0]
    assert set(nh.keys()) == {"name", "history"}
    entry = nh["history"][0]
    assert set(entry.keys()) == {"date", "health_score", "report_count", "top_category"}


def test_health_history_cumulative_includes_pre_window_reports(test_client, db_session):
    """Regression: reports before the query window must affect cumulative health_score."""
    _add_report(db_session, days_ago=60, severity="critical")

    resp = test_client.get("/api/health/history?city=stuttgart&days=3")
    data = resp.json()
    nh = data["neighborhoods"][0]
    # The pre-window report should degrade health_score on all days
    assert all(h["health_score"] < 100 for h in nh["history"])
    # But report_count should be 0 (report is outside the window)
    assert all(h["report_count"] == 0 for h in nh["history"])