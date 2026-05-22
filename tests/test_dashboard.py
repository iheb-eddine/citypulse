"""Tests for Step 5: Dashboard map rendering."""
from app.models import Report


def test_dashboard_empty_db(test_client):
    response = test_client.get("/dashboard")
    assert response.status_code == 200
    assert "No reports yet" in response.text


def test_dashboard_with_reports(test_client, db_session):
    for i in range(5):
        db_session.add(Report(
            photo_path=f"/static/uploads/test{i}.jpg",
            latitude=48.77 + i * 0.001, longitude=9.18,
            category="pothole", severity="low",
            department="roads", description="test",
        ))
    db_session.commit()
    response = test_client.get("/dashboard")
    assert response.status_code == 200
    text = response.text.lower()
    assert "leaflet" in text or "folium" in text


def test_dashboard_marker_colors(test_client, db_session):
    db_session.add(Report(
        photo_path="/static/uploads/crit.jpg",
        latitude=48.7758, longitude=9.1829,
        category="pothole", severity="critical",
        department="roads", description="critical issue",
    ))
    db_session.commit()
    response = test_client.get("/dashboard")
    assert response.status_code == 200
    assert "red" in response.text.lower()


def test_dashboard_pipeline_bar(test_client):
    response = test_client.get("/dashboard")
    assert response.status_code == 200
    assert "pipeline-bar" in response.text
    assert "pipeline-stage" in response.text


def test_dashboard_diffusion_section(test_client):
    response = test_client.get("/dashboard")
    assert response.status_code == 200
    assert "diffusion-section" in response.text
    assert "diffusion-btn" in response.text


def test_dashboard_timelapse_section(test_client):
    response = test_client.get("/dashboard")
    assert response.status_code == 200
    assert "timelapse-section" in response.text
    assert "timelapse-btn" in response.text
