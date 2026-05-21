"""Tests for Granger Causality Cascade Detection."""

from datetime import datetime, timedelta

import numpy as np
import pytest

from app.causality import compute_causality, CORRELATION_THRESHOLD, MAX_LAG
from app.models import Report


def _add_reports(db, city, lat, lng, start, counts):
    """Add reports with given daily counts starting from start date."""
    for i, c in enumerate(counts):
        day = start + timedelta(days=i)
        for _ in range(c):
            db.add(Report(
                photo_path="t.jpg", latitude=lat, longitude=lng,
                city=city, category="pothole", severity="high",
                department="roads", description="t", status="open",
                created_at=day,
            ))
    db.commit()


class TestComputeCausality:
    def test_no_reports(self, db_session):
        result = compute_causality("stuttgart", db_session)
        assert result["city"] == "stuttgart"
        assert result["links"] == []
        assert "proxy" in result["note"]

    def test_single_neighborhood(self, db_session):
        start = datetime(2025, 1, 1)
        _add_reports(db_session, "stuttgart", 48.784, 9.181, start, [1, 2, 3, 4, 5, 6, 7, 8])
        result = compute_causality("stuttgart", db_session)
        assert result["links"] == []

    def test_correlated_pair_detected(self, db_session):
        start = datetime(2025, 1, 1)
        # Hauptbahnhof: spike pattern
        counts_a = [0, 0, 5, 0, 0, 5, 0, 0, 5, 0]
        # Stuttgart-Nord (nearby): same pattern shifted by 1 day
        counts_b = [0, 0, 0, 5, 0, 0, 5, 0, 0, 5]
        _add_reports(db_session, "stuttgart", 48.784, 9.181, start, counts_a)
        _add_reports(db_session, "stuttgart", 48.790, 9.195, start, counts_b)
        result = compute_causality("stuttgart", db_session)
        assert len(result["links"]) > 0
        link = result["links"][0]
        assert link["lag_days"] >= 1
        assert link["correlation"] > CORRELATION_THRESHOLD

    def test_uncorrelated_pair_not_detected(self, db_session):
        start = datetime(2025, 1, 1)
        counts_a = [5, 0, 5, 0, 5, 0, 5, 0, 5, 0]
        counts_b = [1, 1, 1, 1, 1, 1, 1, 1, 1, 1]  # constant — std=0, skipped
        _add_reports(db_session, "stuttgart", 48.784, 9.181, start, counts_a)
        _add_reports(db_session, "stuttgart", 48.790, 9.195, start, counts_b)
        result = compute_causality("stuttgart", db_session)
        assert result["links"] == []

    def test_insufficient_days(self, db_session):
        start = datetime(2025, 1, 1)
        _add_reports(db_session, "stuttgart", 48.784, 9.181, start, [1, 2, 3])
        _add_reports(db_session, "stuttgart", 48.790, 9.195, start, [3, 2, 1])
        result = compute_causality("stuttgart", db_session)
        assert result["links"] == []

    def test_invalid_city_falls_back(self, db_session):
        result = compute_causality("nonexistent", db_session)
        assert result["city"] == "stuttgart"


class TestEndpoint:
    def test_default(self, test_client):
        resp = test_client.get("/api/causality")
        assert resp.status_code == 200
        data = resp.json()
        assert data["city"] == "stuttgart"
        assert "links" in data
        assert "note" in data

    def test_with_city(self, test_client):
        resp = test_client.get("/api/causality?city=berlin")
        assert resp.status_code == 200
        assert resp.json()["city"] == "berlin"

    def test_invalid_city_falls_back(self, test_client):
        resp = test_client.get("/api/causality?city=invalid")
        assert resp.status_code == 200
        assert resp.json()["city"] == "stuttgart"
