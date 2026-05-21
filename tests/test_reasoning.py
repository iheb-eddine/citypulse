"""Tests for Chain-of-Thought severity reasoning."""

from datetime import datetime
from unittest.mock import MagicMock

from app.severity_reasoning import generate_reasoning


def _report(severity="high", category="pothole", description="Large pothole",
            hour=14, **kwargs):
    r = MagicMock()
    r.id = kwargs.get("id", 1)
    r.severity = severity
    r.category = category
    r.description = description
    r.created_at = datetime(2026, 5, 22, hour, 0, 0)
    r.latitude = 48.78
    r.longitude = 9.18
    return r


def test_always_five_steps():
    result = generate_reasoning(_report(), 0)
    assert len(result["reasoning_steps"]) == 5


def test_severity_baseline_critical():
    result = generate_reasoning(_report(severity="critical"), 0)
    step = result["reasoning_steps"][0]
    assert step["factor"] == "severity_baseline"
    assert step["impact"] == "negative"
    assert "5/5" in step["observation"]


def test_severity_baseline_low():
    result = generate_reasoning(_report(severity="low"), 0)
    step = result["reasoning_steps"][0]
    assert step["impact"] == "positive"
    assert "1/5" in step["observation"]


def test_spatial_density_isolated():
    result = generate_reasoning(_report(), 0)
    step = result["reasoning_steps"][1]
    assert step["impact"] == "positive"
    assert "Isolated" in step["observation"]


def test_spatial_density_cluster():
    result = generate_reasoning(_report(), 5)
    step = result["reasoning_steps"][1]
    assert step["impact"] == "negative"
    assert "cluster" in step["observation"]


def test_spatial_density_neutral():
    result = generate_reasoning(_report(), 2)
    step = result["reasoning_steps"][1]
    assert step["impact"] == "neutral"


def test_time_of_day_night():
    result = generate_reasoning(_report(hour=23), 0)
    step = result["reasoning_steps"][2]
    assert step["impact"] == "negative"
    assert "nighttime" in step["observation"]


def test_time_of_day_day():
    result = generate_reasoning(_report(hour=10), 0)
    step = result["reasoning_steps"][2]
    assert step["impact"] == "neutral"
    assert "daytime" in step["observation"]


def test_keywords_found():
    result = generate_reasoning(_report(description="danger of collapse"), 0)
    step = result["reasoning_steps"][3]
    assert step["impact"] == "negative"
    assert "collapse" in step["observation"]
    assert "danger" in step["observation"]


def test_keywords_none():
    result = generate_reasoning(_report(description="minor crack"), 0)
    step = result["reasoning_steps"][3]
    assert step["impact"] == "neutral"


def test_accessibility_high():
    result = generate_reasoning(_report(category="pothole"), 0)
    step = result["reasoning_steps"][4]
    assert step["impact"] == "negative"
    assert "3/3" in step["observation"]


def test_accessibility_low():
    result = generate_reasoning(_report(category="graffiti"), 0)
    step = result["reasoning_steps"][4]
    assert step["impact"] == "positive"


def test_consistent_high_severity():
    result = generate_reasoning(_report(severity="high", description="danger"), 5)
    assert result["consistent"] is True


def test_inconsistent_high_severity():
    result = generate_reasoning(_report(severity="high", category="graffiti",
                                        description="minor tag"), 0)
    assert result["consistent"] is False


def test_medium_always_consistent():
    result = generate_reasoning(_report(severity="medium"), 0)
    assert result["consistent"] is True


def test_conclusion_inconsistent():
    result = generate_reasoning(_report(severity="high", category="graffiti",
                                        description="small"), 0)
    assert "re-evaluation" in result["conclusion"]


def test_endpoint_404(test_client):
    resp = test_client.get("/api/reports/9999/reasoning")
    assert resp.status_code == 404


def test_endpoint_success(test_client, db_session):
    from app.models import Report
    r = Report(id=1, photo_path="x.jpg", latitude=48.78, longitude=9.18,
               city="stuttgart", category="pothole", severity="high",
               department="roads", description="Large pothole on road",
               created_at=datetime(2026, 5, 22, 14, 0, 0))
    db_session.add(r)
    db_session.commit()
    resp = test_client.get("/api/reports/1/reasoning")
    assert resp.status_code == 200
    data = resp.json()
    assert data["report_id"] == 1
    assert data["severity"] == "high"
    assert len(data["reasoning_steps"]) == 5
    assert "consistent" in data
    assert "conclusion" in data
