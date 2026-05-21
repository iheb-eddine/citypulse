"""CityPulse Graph Diffusion Prediction — heat equation on neighborhood graph."""

from math import radians, sin, cos, sqrt, atan2

import numpy as np
from scipy.linalg import expm
from sqlalchemy.orm import Session

from app.config import CITIES, get_city, neighborhood_for_coords
from app.models import Report

DIFFUSION_THRESHOLD_KM = 3.0
DIFFUSIVITY = 0.01


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Haversine distance in kilometers between two points."""
    r = 6371.0
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return r * 2 * atan2(sqrt(a), sqrt(1 - a))


def _get_centroids(city_key: str) -> list[tuple[str, float, float]]:
    """Return (name, lat, lng) centroids for each neighborhood."""
    cfg = CITIES[city_key]
    centroids = []
    for lat_min, lat_max, lng_min, lng_max, name in cfg["neighborhoods"]:
        centroids.append((name, (lat_min + lat_max) / 2, (lng_min + lng_max) / 2))
    return centroids


def build_adjacency(centroids: list[tuple[str, float, float]]) -> np.ndarray:
    """Build binary adjacency matrix from centroid proximity."""
    n = len(centroids)
    A = np.zeros((n, n))
    for i in range(n):
        for j in range(i + 1, n):
            d = haversine_km(centroids[i][1], centroids[i][2], centroids[j][1], centroids[j][2])
            if d < DIFFUSION_THRESHOLD_KM:
                A[i, j] = A[j, i] = 1.0
    return A


def compute_diffusion(city_key: str, horizon: int, db: Session) -> dict:
    """Compute diffusion prediction for a city at a given time horizon."""
    city_key, _ = get_city(city_key)
    centroids = _get_centroids(city_key)
    n = len(centroids)

    # Build graph
    A = build_adjacency(centroids)
    D = np.diag(A.sum(axis=1))
    L = D - A

    # Query current open reports per neighborhood
    reports = db.query(Report).filter(
        Report.city == city_key, Report.status != "resolved"
    ).all()

    # Count reports per neighborhood
    counts = np.zeros(n)
    name_to_idx = {c[0]: i for i, c in enumerate(centroids)}
    for r in reports:
        nh = neighborhood_for_coords(r.latitude, r.longitude, city_key)
        if nh in name_to_idx:
            counts[name_to_idx[nh]] += 1

    # Solve heat equation: u(t) = expm(-α * t * L) @ u(0)
    u_t = expm(-DIFFUSIVITY * horizon * L) @ counts

    # Build response
    predictions = []
    for i, (name, lat, lng) in enumerate(centroids):
        predictions.append({
            "neighborhood": name,
            "lat": lat,
            "lng": lng,
            "current_reports": int(counts[i]),
            "predicted_rate": round(float(u_t[i]), 2),
        })

    edge_count = int(A.sum()) // 2
    return {
        "city": city_key,
        "horizon_days": horizon,
        "predictions": predictions,
        "graph": {"nodes": n, "edges": edge_count, "threshold_km": DIFFUSION_THRESHOLD_KM},
    }
