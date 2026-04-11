"""CityPulse analytics — scoring, trends, clustering, and risk computation."""

from collections import Counter
from datetime import datetime, timedelta
from typing import Optional

import numpy as np
from sqlalchemy.orm import Session

from app.config import (
    SEVERITY_WEIGHTS, ACCESSIBILITY_WEIGHTS,
    _SEVERITY_BASE_DAYS, _CATEGORY_EXTRA_DAYS,
    get_city, neighborhood_for_coords,
)
from app.models import Report


def estimate_resolution_days(category: str, severity: str) -> int:
    return _SEVERITY_BASE_DAYS.get(severity, 5) + _CATEGORY_EXTRA_DAYS.get(category, 0)


def compute_health_score(reports: list) -> float:
    if not reports:
        return 100
    weighted_sum = sum(SEVERITY_WEIGHTS.get(r.severity, 1) for r in reports)
    return max(0, 100 - (weighted_sum / len(reports)) * 20)


def compute_trend(reports: list, now: Optional[datetime] = None) -> int:
    now = now or datetime.now()
    week_ago = now - timedelta(days=7)
    two_weeks_ago = now - timedelta(days=14)
    current = sum(1 for r in reports if r.created_at >= week_ago)
    previous = sum(1 for r in reports if two_weeks_ago <= r.created_at < week_ago)
    return current - previous


def compute_category_breakdown(reports: list) -> dict:
    return dict(Counter(r.category for r in reports))


def compute_severity_breakdown(reports: list) -> dict:
    return dict(Counter(r.severity for r in reports))


def compute_accessibility_score(reports: list) -> float:
    if not reports:
        return 100
    weighted_sum = sum(
        ACCESSIBILITY_WEIGHTS.get(r.category, 1) * SEVERITY_WEIGHTS.get(r.severity, 1)
        for r in reports
    )
    max_possible = len(reports) * 3 * 5
    return max(0, 100 - (weighted_sum / max_possible) * 100)


def compute_top_accessibility_categories(reports: list) -> list:
    totals: dict[str, float] = {}
    for r in reports:
        w = ACCESSIBILITY_WEIGHTS.get(r.category, 1) * SEVERITY_WEIGHTS.get(r.severity, 1)
        totals[r.category] = totals.get(r.category, 0) + w
    return sorted(totals, key=totals.get, reverse=True)


def compute_risk_scores(reports: list, city_key: Optional[str] = None) -> list:
    """Compute per-neighborhood risk scores (0-100) from report data."""
    if not reports:
        return []
    _, cfg = get_city(city_key)
    now = datetime.now()
    week_ago = now - timedelta(days=7)
    two_weeks_ago = now - timedelta(days=14)

    nh_reports: dict[str, list] = {}
    for nb in cfg["neighborhoods"]:
        lat_min, lat_max, lng_min, lng_max, name = nb
        matched = [r for r in reports if lat_min <= r.latitude <= lat_max and lng_min <= r.longitude <= lng_max]
        if matched:
            nh_reports[name] = matched

    if not nh_reports:
        return []

    max_count = max(len(v) for v in nh_reports.values())
    results = []
    for nb in cfg["neighborhoods"]:
        lat_min, lat_max, lng_min, lng_max, name = nb
        reps = nh_reports.get(name)
        if not reps:
            continue
        count = len(reps)
        avg_sev = sum(SEVERITY_WEIGHTS.get(r.severity, 1) for r in reps) / count
        unresolved = sum(1 for r in reps if r.status != "resolved") / count
        this_week = sum(1 for r in reps if r.created_at >= week_ago)
        last_week = sum(1 for r in reps if two_weeks_ago <= r.created_at < week_ago)
        trend_f = 1.0 if this_week > last_week else (0.5 if this_week == last_week else 0.0)
        risk = ((count / max_count) * 0.4 + (avg_sev / 5) * 0.3 + unresolved * 0.2 + trend_f * 0.1) * 100
        risk = min(100, max(0, round(risk, 1)))
        color = "#2e7d32" if risk <= 33 else ("#f9a825" if risk <= 66 else "#c62828")
        lat_c = (lat_min + lat_max) / 2
        lng_c = (lng_min + lng_max) / 2
        grade = "A" if risk <= 20 else "B" if risk <= 40 else "C" if risk <= 60 else "D" if risk <= 80 else "F"
        results.append({"name": name, "lat": lat_c, "lng": lng_c, "risk_score": risk, "color": color, "grade": grade})
    results.sort(key=lambda x: x["risk_score"], reverse=True)
    return results


def compute_hotspots(reports: list, city_key: Optional[str] = None) -> list:
    clusters = Counter(r.cluster_id for r in reports if r.cluster_id is not None)
    hotspots = []
    for cid, cnt in clusters.most_common(3):
        cluster_reports = [r for r in reports if r.cluster_id == cid]
        avg_lat = sum(r.latitude for r in cluster_reports) / len(cluster_reports)
        avg_lng = sum(r.longitude for r in cluster_reports) / len(cluster_reports)
        name = neighborhood_for_coords(avg_lat, avg_lng, city_key)
        hotspots.append({"cluster_id": cid, "count": cnt, "name": name})
    return hotspots


_last_cluster_count: int = -1


def run_clustering(reports: list[Report], db: Session) -> None:
    """Run DBSCAN on report coordinates and update cluster_id in DB."""
    global _last_cluster_count
    if not reports:
        return
    if len(reports) == _last_cluster_count:
        return
    from sklearn.cluster import DBSCAN
    coords = np.array([[r.latitude, r.longitude] for r in reports])
    labels = DBSCAN(eps=0.003, min_samples=3, metric="euclidean").fit_predict(coords)
    for report, label in zip(reports, labels):
        report.cluster_id = None if label == -1 else int(label)
    db.commit()
    _last_cluster_count = len(reports)
