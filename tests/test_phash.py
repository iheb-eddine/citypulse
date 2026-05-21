"""Tests for pHash duplicate detection."""

import io
import pytest
from unittest.mock import patch
from PIL import Image

from app.phash import compute_phash, _hamming, find_duplicates, _hash_cache


def _make_image(color: tuple, size=(64, 64)) -> bytes:
    img = Image.new("RGB", size, color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


class TestComputePhash:
    def test_deterministic(self):
        img = _make_image((100, 150, 200))
        assert compute_phash(img) == compute_phash(img)

    def test_returns_64bit_int(self):
        h = compute_phash(_make_image((50, 50, 50)))
        assert 0 <= h < 2**64

    def test_different_images_different_hashes(self):
        h1 = compute_phash(_make_image((0, 0, 0)))
        h2 = compute_phash(_make_image((255, 255, 255)))
        assert h1 != h2

    def test_similar_images_low_distance(self):
        h1 = compute_phash(_make_image((100, 100, 100)))
        h2 = compute_phash(_make_image((102, 100, 100)))
        assert _hamming(h1, h2) <= 10


class TestHamming:
    def test_identical(self):
        assert _hamming(0b1010, 0b1010) == 0

    def test_all_different(self):
        assert _hamming(0b0000, 0b1111) == 4

    def test_one_bit(self):
        assert _hamming(0b1000, 0b0000) == 1


class TestFindDuplicatesEndpoint:
    def test_not_found(self, test_client):
        resp = test_client.get("/api/reports/9999/duplicates")
        assert resp.status_code == 404

    def test_returns_list(self, test_client, db_session, tmp_path):
        # Create two reports with the same image on disk
        img_bytes = _make_image((80, 80, 80))
        img_file = tmp_path / "test.jpg"
        img_file.write_bytes(img_bytes)

        from app.models import Report
        from app.phash import _hash_cache, _BASE_DIR
        import app.phash as phash_mod

        # Reset cache
        _hash_cache.clear()
        phash_mod._cache_loaded = False

        r1 = Report(photo_path="/static/uploads/a.jpg", latitude=48.0, longitude=9.0,
                    city="stuttgart", category="pothole", severity="high",
                    department="roads", description="test1")
        r2 = Report(photo_path="/static/uploads/b.jpg", latitude=48.0, longitude=9.0,
                    city="stuttgart", category="pothole", severity="high",
                    department="roads", description="test2")
        db_session.add_all([r1, r2])
        db_session.commit()

        # Write image files where phash expects them
        upload_dir = _BASE_DIR / "static" / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        (upload_dir / "a.jpg").write_bytes(img_bytes)
        (upload_dir / "b.jpg").write_bytes(img_bytes)

        try:
            resp = test_client.get(f"/api/reports/{r1.id}/duplicates")
            assert resp.status_code == 200
            data = resp.json()
            assert any(d["id"] == r2.id and d["distance"] == 0 for d in data)
        finally:
            (upload_dir / "a.jpg").unlink(missing_ok=True)
            (upload_dir / "b.jpg").unlink(missing_ok=True)
            _hash_cache.clear()
            phash_mod._cache_loaded = False

    def test_no_duplicates_for_dissimilar(self, test_client, db_session, tmp_path):
        from app.models import Report
        from app.phash import _hash_cache, _BASE_DIR
        import app.phash as phash_mod

        _hash_cache.clear()
        phash_mod._cache_loaded = False

        # Create images with distinct frequency content (not solid colors)
        import numpy as np
        img1 = Image.fromarray(np.random.RandomState(1).randint(0, 256, (128, 128, 3), dtype=np.uint8))
        img2 = Image.fromarray(np.random.RandomState(999).randint(0, 256, (128, 128, 3), dtype=np.uint8))
        buf1, buf2 = io.BytesIO(), io.BytesIO()
        img1.save(buf1, format="JPEG")
        img2.save(buf2, format="JPEG")

        r1 = Report(photo_path="/static/uploads/rand1.jpg", latitude=48.0, longitude=9.0,
                    city="stuttgart", category="pothole", severity="high",
                    department="roads", description="rand1")
        r2 = Report(photo_path="/static/uploads/rand2.jpg", latitude=48.0, longitude=9.0,
                    city="stuttgart", category="pothole", severity="high",
                    department="roads", description="rand2")
        db_session.add_all([r1, r2])
        db_session.commit()

        upload_dir = _BASE_DIR / "static" / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        (upload_dir / "rand1.jpg").write_bytes(buf1.getvalue())
        (upload_dir / "rand2.jpg").write_bytes(buf2.getvalue())

        try:
            resp = test_client.get(f"/api/reports/{r1.id}/duplicates")
            assert resp.status_code == 200
            data = resp.json()
            assert not any(d["id"] == r2.id for d in data)
        finally:
            (upload_dir / "rand1.jpg").unlink(missing_ok=True)
            (upload_dir / "rand2.jpg").unlink(missing_ok=True)
            _hash_cache.clear()
            phash_mod._cache_loaded = False


class TestSimilarityClusters:
    """Tests for find_similarity_clusters and the endpoint."""

    def _make_reports(self, db_session, city, n):
        from app.models import Report
        reports = []
        for i in range(n):
            r = Report(
                photo_path=f"/static/uploads/sc{i}.jpg", latitude=48.7 + i * 0.001,
                longitude=9.1, city=city, category="graffiti" if i % 2 == 0 else "pothole",
                severity="high", department="roads", description=f"sc{i}",
            )
            db_session.add(r)
            reports.append(r)
        db_session.commit()
        return reports

    def test_empty_city(self, db_session):
        from app.phash import find_similarity_clusters, _hash_cache
        _hash_cache.clear()
        result = find_similarity_clusters("nonexistent_city", 12, db_session)
        assert result == []

    def test_no_similar_reports(self, db_session):
        from app.phash import find_similarity_clusters, _hash_cache
        _hash_cache.clear()
        reports = self._make_reports(db_session, "stuttgart", 3)
        # Hashes far apart (>32 bits different)
        _hash_cache[reports[0].id] = 0
        _hash_cache[reports[1].id] = (1 << 64) - 1  # all bits flipped
        _hash_cache[reports[2].id] = 0xAAAAAAAAAAAAAAAA
        with patch("app.phash._ensure_cache"):
            result = find_similarity_clusters("stuttgart", 12, db_session)
        assert result == []

    def test_two_similar(self, db_session):
        from app.phash import find_similarity_clusters, _hash_cache
        _hash_cache.clear()
        reports = self._make_reports(db_session, "stuttgart", 2)
        _hash_cache[reports[0].id] = 0b1111000011110000
        _hash_cache[reports[1].id] = 0b1111000011110001  # distance = 1
        with patch("app.phash._ensure_cache"):
            result = find_similarity_clusters("stuttgart", 12, db_session)
        assert len(result) == 1
        assert set(result[0]["report_ids"]) == {reports[0].id, reports[1].id}
        assert result[0]["avg_hamming_distance"] == 1.0

    def test_transitive_clustering(self, db_session):
        from app.phash import find_similarity_clusters, _hash_cache
        _hash_cache.clear()
        reports = self._make_reports(db_session, "stuttgart", 3)
        # A~B (dist=5), B~C (dist=5), A~C (dist=10) — all within threshold=12
        _hash_cache[reports[0].id] = 0b0000000000000000
        _hash_cache[reports[1].id] = 0b0000000000011111  # dist 5 from A
        _hash_cache[reports[2].id] = 0b0000001111100000  # dist 5 from B, dist 10 from A
        with patch("app.phash._ensure_cache"):
            result = find_similarity_clusters("stuttgart", 12, db_session)
        assert len(result) == 1
        assert set(result[0]["report_ids"]) == {r.id for r in reports}

    def test_singleton_excluded(self, db_session):
        from app.phash import find_similarity_clusters, _hash_cache
        _hash_cache.clear()
        reports = self._make_reports(db_session, "stuttgart", 3)
        _hash_cache[reports[0].id] = 0
        _hash_cache[reports[1].id] = 1  # dist 1 from reports[0]
        _hash_cache[reports[2].id] = (1 << 64) - 1  # far from both
        with patch("app.phash._ensure_cache"):
            result = find_similarity_clusters("stuttgart", 12, db_session)
        assert len(result) == 1
        assert reports[2].id not in result[0]["report_ids"]

    def test_threshold_boundary(self, db_session):
        from app.phash import find_similarity_clusters, _hash_cache
        _hash_cache.clear()
        reports = self._make_reports(db_session, "stuttgart", 2)
        _hash_cache[reports[0].id] = 0
        _hash_cache[reports[1].id] = 0b111111111111  # distance = 12
        with patch("app.phash._ensure_cache"):
            # Exactly at threshold=12 → included
            result = find_similarity_clusters("stuttgart", 12, db_session)
            assert len(result) == 1
            # threshold=11 → excluded
            result = find_similarity_clusters("stuttgart", 11, db_session)
            assert result == []

    def test_endpoint_invalid_threshold(self, test_client):
        resp = test_client.get("/api/reports/similarity-clusters?threshold=-1")
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "INVALID_THRESHOLD"
        resp = test_client.get("/api/reports/similarity-clusters?threshold=33")
        assert resp.status_code == 422

    def test_endpoint_returns_clusters_with_enrichment(self, test_client, db_session):
        from app.phash import _hash_cache
        import app.phash as phash_mod
        from app.models import Report

        _hash_cache.clear()
        # Create reports with known categories
        r1 = Report(
            photo_path="/static/uploads/e1.jpg", latitude=48.77, longitude=9.17,
            city="stuttgart", category="graffiti", severity="high",
            department="sanitation", description="e1",
        )
        r2 = Report(
            photo_path="/static/uploads/e2.jpg", latitude=48.77, longitude=9.17,
            city="stuttgart", category="graffiti", severity="high",
            department="sanitation", description="e2",
        )
        r3 = Report(
            photo_path="/static/uploads/e3.jpg", latitude=48.77, longitude=9.17,
            city="stuttgart", category="pothole", severity="high",
            department="roads", description="e3",
        )
        db_session.add_all([r1, r2, r3])
        db_session.commit()

        _hash_cache[r1.id] = 0
        _hash_cache[r2.id] = 1  # dist 1 from r1
        _hash_cache[r3.id] = 3  # dist 2 from r1, dist 1 from r2

        with patch("app.phash._ensure_cache"):
            resp = test_client.get("/api/reports/similarity-clusters?city=stuttgart&threshold=12")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total_clusters"] == 1
        assert data["threshold"] == 12
        assert data["city"] == "stuttgart"
        cluster = data["clusters"][0]
        assert cluster["cluster_id"] == 1
        assert cluster["size"] == 3
        assert set(cluster["report_ids"]) == {r1.id, r2.id, r3.id}
        # common_category: 2 graffiti vs 1 pothole → graffiti
        assert cluster["common_category"] == "graffiti"
        assert cluster["common_neighborhood"] is not None
        _hash_cache.clear()
