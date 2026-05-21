"""Perceptual hashing (pHash) for duplicate image detection."""

from pathlib import Path

import numpy as np
from PIL import Image
from scipy.fft import dctn

from app.models import Report

_hash_cache: dict[int, int] = {}

_BASE_DIR = Path(__file__).resolve().parent


def compute_phash(image_bytes: bytes) -> int:
    """Compute 64-bit perceptual hash from image bytes."""
    img = Image.open(__import__("io").BytesIO(image_bytes)).convert("L").resize((32, 32))
    pixels = np.asarray(img, dtype=np.float64)
    dct = dctn(pixels, type=2)
    low = dct[:8, :8].flatten()
    med = np.median(low)
    return int("".join("1" if v > med else "0" for v in low), 2)


def _hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def _ensure_cache(db) -> None:
    """Load hashes for any reports not yet in cache."""
    reports = db.query(Report.id, Report.photo_path).all()
    for rid, photo_path in reports:
        if rid in _hash_cache:
            continue
        fpath = _BASE_DIR / photo_path.lstrip("/")
        if not fpath.exists():
            continue
        try:
            _hash_cache[rid] = compute_phash(fpath.read_bytes())
        except Exception:
            continue


def find_similarity_clusters(city: str, threshold: int, db) -> list[dict]:
    """Find connected components of visually similar reports in a city."""
    _ensure_cache(db)
    city_ids = {r.id for r in db.query(Report.id).filter(Report.city == city).all()}
    subset = {rid: h for rid, h in _hash_cache.items() if rid in city_ids}
    ids = list(subset.keys())
    adj: dict[int, list[int]] = {rid: [] for rid in ids}
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            if _hamming(subset[ids[i]], subset[ids[j]]) <= threshold:
                adj[ids[i]].append(ids[j])
                adj[ids[j]].append(ids[i])
    visited: set[int] = set()
    clusters = []
    for rid in ids:
        if rid in visited:
            continue
        queue = [rid]
        visited.add(rid)
        component = []
        while queue:
            node = queue.pop(0)
            component.append(node)
            for nb in adj[node]:
                if nb not in visited:
                    visited.add(nb)
                    queue.append(nb)
        if len(component) < 2:
            continue
        edges = []
        for i in range(len(component)):
            for j in range(i + 1, len(component)):
                d = _hamming(subset[component[i]], subset[component[j]])
                if d <= threshold:
                    edges.append(d)
        avg = sum(edges) / len(edges) if edges else 0.0
        clusters.append({"report_ids": component, "avg_hamming_distance": round(avg, 1)})
    return clusters


def find_duplicates(report_id: int, db, threshold: int = 10) -> list[dict]:
    """Find reports with similar images (Hamming distance <= threshold)."""
    _ensure_cache(db)
    if report_id not in _hash_cache:
        report = db.query(Report).filter(Report.id == report_id).first()
        if not report:
            return []
        fpath = _BASE_DIR / report.photo_path.lstrip("/")
        if not fpath.exists():
            return []
        _hash_cache[report_id] = compute_phash(fpath.read_bytes())

    target_hash = _hash_cache[report_id]
    results = []
    for rid, h in _hash_cache.items():
        if rid == report_id:
            continue
        dist = _hamming(target_hash, h)
        if dist <= threshold:
            results.append({"id": rid, "distance": dist})
    results.sort(key=lambda x: x["distance"])
    return results
