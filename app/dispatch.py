"""Crew Dispatch Optimizer — K-means clustering + nearest-neighbor TSP + 2-opt."""

import numpy as np
from sklearn.cluster import KMeans
from sqlalchemy.orm import Session

from app.models import Report

DEFAULT_CREWS = 3


def _haversine_matrix(lats: np.ndarray, lngs: np.ndarray) -> np.ndarray:
    """Compute NxN distance matrix (km) using vectorized Haversine."""
    lat_r = np.radians(lats)
    lng_r = np.radians(lngs)
    dlat = lat_r[:, None] - lat_r[None, :]
    dlng = lng_r[:, None] - lng_r[None, :]
    a = np.sin(dlat / 2) ** 2 + np.cos(lat_r[:, None]) * np.cos(lat_r[None, :]) * np.sin(dlng / 2) ** 2
    return 6371.0 * 2 * np.arcsin(np.sqrt(a))


def _nearest_neighbor_route(dist_matrix: np.ndarray, start: int) -> list:
    """Greedy nearest-neighbor TSP from start node. Returns ordered indices."""
    n = dist_matrix.shape[0]
    visited = [start]
    unvisited = set(range(n)) - {start}
    while unvisited:
        last = visited[-1]
        nearest = min(unvisited, key=lambda x: dist_matrix[last, x])
        visited.append(nearest)
        unvisited.remove(nearest)
    return visited


def _two_opt(route: list, dist_matrix: np.ndarray) -> list:
    """Open-path 2-opt improvement. Never increases total distance."""
    route = list(route)
    n = len(route)
    if n < 3:
        return route
    improved = True
    while improved:
        improved = False
        for i in range(n - 2):
            for j in range(i + 2, n - 1):
                d_old = dist_matrix[route[i], route[i + 1]] + dist_matrix[route[j], route[j + 1]]
                d_new = dist_matrix[route[i], route[j]] + dist_matrix[route[i + 1], route[j + 1]]
                if d_new < d_old:
                    route[i + 1:j + 1] = route[i + 1:j + 1][::-1]
                    improved = True
    return route


def _route_distance(route: list, dist_matrix: np.ndarray) -> float:
    """Sum of consecutive distances along route."""
    return sum(dist_matrix[route[i], route[i + 1]] for i in range(len(route) - 1))


def optimize_dispatch(city: str, num_crews: int, db: Session) -> dict:
    """Main entry: cluster open issues into crews, route each crew."""
    issues = db.query(Report).filter(Report.city == city, Report.status == "open").all()
    n = len(issues)

    if n == 0:
        return {"city": city, "total_issues": 0, "num_crews": num_crews,
                "total_distance_km": 0.0, "crews": []}

    lats = np.array([r.latitude for r in issues])
    lngs = np.array([r.longitude for r in issues])
    dist_matrix = _haversine_matrix(lats, lngs)

    # Assign clusters
    k = min(num_crews, n)
    if k >= n:
        labels = np.arange(n)
        centroids = np.column_stack([lats, lngs])
    else:
        km = KMeans(n_clusters=k, random_state=42, n_init=10).fit(np.column_stack([lats, lngs]))
        labels = km.labels_
        centroids = km.cluster_centers_

    crews = []
    total_dist = 0.0

    for c in range(num_crews):
        indices = [i for i, l in enumerate(labels) if l == c]
        if not indices:
            crews.append({"crew_id": c, "num_issues": 0, "route_distance_km": 0.0, "route": []})
            continue

        if len(indices) == 1:
            route_indices = indices
            route_dist = 0.0
        else:
            # Find start: issue nearest to centroid
            centroid = centroids[c] if c < len(centroids) else centroids[0]
            local_dists = [(lats[i] - centroid[0]) ** 2 + (lngs[i] - centroid[1]) ** 2 for i in indices]
            start_local = int(np.argmin(local_dists))

            # Build sub-distance-matrix
            sub_dist = dist_matrix[np.ix_(indices, indices)]
            local_route = _nearest_neighbor_route(sub_dist, start_local)
            local_route = _two_opt(local_route, sub_dist)
            route_indices = [indices[lr] for lr in local_route]
            route_dist = _route_distance(local_route, sub_dist)

        total_dist += route_dist
        route_items = []
        for order, idx in enumerate(route_indices):
            issue = issues[idx]
            route_items.append({
                "issue_id": issue.id, "latitude": issue.latitude,
                "longitude": issue.longitude, "severity": issue.severity,
                "department": issue.department, "order": order,
            })
        crews.append({"crew_id": c, "num_issues": len(indices),
                      "route_distance_km": round(route_dist, 2), "route": route_items})

    return {"city": city, "total_issues": n, "num_crews": num_crews,
            "total_distance_km": round(total_dist, 2), "crews": crews}
