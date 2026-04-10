"""Tests for Step 2 routes: home, dashboard, and API reports placeholder."""


def test_home_returns_200_html(test_client):
    response = test_client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_dashboard_returns_200_html(test_client):
    response = test_client.get("/dashboard")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_api_reports_returns_empty_list(test_client):
    response = test_client.get("/api/reports")
    assert response.status_code == 200
    assert response.json() == []
