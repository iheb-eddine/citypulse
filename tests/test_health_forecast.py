"""Tests for the Health Score Forecast endpoint."""

from datetime import datetime, timedelta

from app.models import Report


def _add_report(db, severity="high", days_ago=0):
    r = Report(
        photo_path="test.jpg", latitude=48.783, longitude=9.180,
        city="stuttgart", category="pothole", severity=severity,
        department="roads", description="test",
        created_at=datetime.now() - timedelta(days=days_ago),
    )
    db.add(r)
    db.commit()
    return r


def test_forecast_empty(test_client, db_session):
    resp = test_client.get("/api/health/forecast?city=stuttgart")
    assert resp.status_code == 200
    data = resp.json()
    assert data["city"] == "stuttgart"
    assert data["trend"] == "stable"
    assert data["current_score"] == 100.0
    assert len(data["forecast"]) == 7
    assert all(f["predicted_score"] == 100.0 for f in data["forecast"])


def test_forecast_response_structure(test_client, db_session):
    _add_report(db_session, days_ago=5)
    resp = test_client.get("/api/health/forecast?city=stuttgart")
    data = resp.json()
    assert set(data.keys()) == {"city", "trend", "slope", "current_score", "forecast"}
    f = data["forecast"][0]
    assert set(f.keys()) == {"day", "date", "predicted_score"}
    assert f["day"] == 1


def test_forecast_declining_trend(test_client, db_session):
    # Add progressively more severe reports over recent days to create declining trend
    for i in range(14):
        for _ in range(i):  # more reports on recent days
            _add_report(db_session, severity="critical", days_ago=13 - i)
    resp = test_client.get("/api/health/forecast?city=stuttgart&history_days=14")
    data = resp.json()
    assert data["trend"] == "declining"
    assert data["slope"] < -0.5


def test_forecast_clamped_to_bounds(test_client, db_session):
    # Many reports to push score toward 0, forecast should not go below 0
    for i in range(50):
        _add_report(db_session, severity="critical", days_ago=0)
    resp = test_client.get("/api/health/forecast?city=stuttgart&history_days=2&forecast_days=30")
    data = resp.json()
    assert all(0 <= f["predicted_score"] <= 100 for f in data["forecast"])


def test_forecast_params_clamped(test_client, db_session):
    resp = test_client.get("/api/health/forecast?city=stuttgart&history_days=1&forecast_days=0")
    data = resp.json()
    # history_days clamped to 2, forecast_days clamped to 1
    assert len(data["forecast"]) == 1


def test_forecast_custom_params(test_client, db_session):
    _add_report(db_session, days_ago=3)
    resp = test_client.get("/api/health/forecast?city=stuttgart&history_days=5&forecast_days=3")
    data = resp.json()
    assert len(data["forecast"]) == 3


def test_forecast_dates_sequential(test_client, db_session):
    resp = test_client.get("/api/health/forecast?city=stuttgart&forecast_days=5")
    data = resp.json()
    today = datetime.now().date()
    for i, f in enumerate(data["forecast"], 1):
        expected = (today + timedelta(days=i)).strftime("%Y-%m-%d")
        assert f["date"] == expected
        assert f["day"] == i
