"""Granger Causality Cascade Detection — cross-correlation proxy."""

from collections import defaultdict

import numpy as np
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import get_city, neighborhood_for_coords
from app.models import Report

CORRELATION_THRESHOLD = 0.5
MAX_LAG = 7


def compute_causality(city_key: str, db: Session) -> dict:
    """Compute causal links between neighborhoods using cross-correlation."""
    city_key, cfg = get_city(city_key)
    neighborhoods = [n[4] for n in cfg["neighborhoods"]]

    # Query reports with date and coordinates
    reports = (
        db.query(Report.latitude, Report.longitude, func.date(Report.created_at).label("day"))
        .filter(Report.city == city_key)
        .all()
    )

    if not reports:
        return {"city": city_key, "links": [], "note": "cross-correlation proxy, not full VAR Granger test"}

    # Build daily counts per neighborhood
    counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    all_days: set[str] = set()
    for lat, lng, day in reports:
        nh = neighborhood_for_coords(lat, lng, city_key)
        if nh in neighborhoods:
            counts[nh][str(day)] += 1
            all_days.add(str(day))

    if len(all_days) < 4:
        return {"city": city_key, "links": [], "note": "cross-correlation proxy, not full VAR Granger test"}

    # Build sorted day index and time series arrays
    sorted_days = sorted(all_days)
    series: dict[str, np.ndarray] = {}
    for nh in neighborhoods:
        if nh in counts:
            series[nh] = np.array([counts[nh].get(d, 0) for d in sorted_days], dtype=float)

    # Compute cross-correlation for each pair
    links = []
    nh_list = list(series.keys())
    for i, src in enumerate(nh_list):
        x = series[src]
        if x.std() == 0:
            continue
        for tgt in nh_list:
            if tgt == src:
                continue
            y = series[tgt]
            if y.std() == 0:
                continue
            for k in range(1, MAX_LAG + 1):
                if len(x) - k < 3:
                    break
                r = float(np.corrcoef(x[:-k], y[k:])[0, 1])
                if r > CORRELATION_THRESHOLD:
                    links.append({"source": src, "target": tgt, "lag_days": k, "correlation": round(r, 3)})
                    break  # report strongest (smallest) lag per pair

    links.sort(key=lambda l: l["correlation"], reverse=True)
    return {"city": city_key, "links": links, "note": "cross-correlation proxy, not full VAR Granger test"}
