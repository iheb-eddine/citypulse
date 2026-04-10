"""Tests for Step 7: Health score, trend, category breakdown, hotspots."""
from datetime import datetime, timedelta

from app.main import compute_health_score, compute_trend
from app.models import Report


def _report(severity="low", created_at=None, **kw):
    return Report(
        photo_path="/static/uploads/t.jpg", latitude=48.77, longitude=9.18,
        category=kw.get("category", "pothole"), severity=severity,
        department="roads", description="t",
        created_at=created_at or datetime.now(),
    )


# --- Health score tests ---

def test_health_score_no_reports():
    assert compute_health_score([]) == 100


def test_health_score_all_low():
    assert compute_health_score([_report("low") for _ in range(10)]) == 80


def test_health_score_all_critical():
    assert compute_health_score([_report("critical") for _ in range(10)]) == 0


def test_health_score_mixed():
    reports = [_report("low") for _ in range(5)] + [_report("high") for _ in range(5)]
    assert compute_health_score(reports) == 60


def test_health_score_floor_at_zero():
    # 2 critical: weighted_sum=10, 10/2*20=100, 100-100=0
    assert compute_health_score([_report("critical") for _ in range(2)]) == 0


# --- Trend tests ---

def test_trend_more_recent():
    now = datetime.now()
    reports = (
        [_report(created_at=now - timedelta(days=2)) for _ in range(5)]
        + [_report(created_at=now - timedelta(days=10)) for _ in range(2)]
    )
    assert compute_trend(reports, now=now) == 3


def test_trend_fewer_recent():
    now = datetime.now()
    reports = (
        [_report(created_at=now - timedelta(days=2)) for _ in range(1)]
        + [_report(created_at=now - timedelta(days=10)) for _ in range(4)]
    )
    assert compute_trend(reports, now=now) == -3


def test_trend_equal():
    now = datetime.now()
    reports = (
        [_report(created_at=now - timedelta(days=2)) for _ in range(3)]
        + [_report(created_at=now - timedelta(days=10)) for _ in range(3)]
    )
    assert compute_trend(reports, now=now) == 0


def test_trend_no_reports():
    assert compute_trend([], now=datetime.now()) == 0
