"""Tests for Step 6: DBSCAN clustering."""
from app.main import run_clustering
from app.models import Report


def _make_report(lat, lng):
    return Report(
        photo_path="/static/uploads/test.jpg",
        latitude=lat, longitude=lng,
        category="pothole", severity="low",
        department="roads", description="test",
    )


def test_cluster_empty_reports(db_session):
    run_clustering([], db_session)


def test_cluster_single_report(db_session):
    r = _make_report(48.77, 9.18)
    db_session.add(r)
    db_session.commit()
    reports = db_session.query(Report).all()
    run_clustering(reports, db_session)
    assert reports[0].cluster_id is None


def test_cluster_two_nearby_reports(db_session):
    for i in range(2):
        db_session.add(_make_report(48.77 + i * 0.001, 9.18))
    db_session.commit()
    reports = db_session.query(Report).all()
    run_clustering(reports, db_session)
    assert all(r.cluster_id is None for r in reports)


def test_cluster_three_nearby_reports(db_session):
    for i in range(3):
        db_session.add(_make_report(48.77 + i * 0.001, 9.18))
    db_session.commit()
    reports = db_session.query(Report).all()
    run_clustering(reports, db_session)
    ids = [r.cluster_id for r in reports]
    assert all(c is not None for c in ids)
    assert len(set(ids)) == 1


def test_cluster_separated_groups(db_session):
    for i in range(3):
        db_session.add(_make_report(48.77 + i * 0.001, 9.18))
    for i in range(3):
        db_session.add(_make_report(48.80 + i * 0.001, 9.21))
    db_session.commit()
    reports = db_session.query(Report).all()
    run_clustering(reports, db_session)
    ids = [r.cluster_id for r in reports]
    assert all(c is not None for c in ids)
    assert len(set(ids)) == 2
    assert set(ids[:3]) != set(ids[3:])


def test_cluster_mixed_noise_and_cluster(db_session):
    for i in range(3):
        db_session.add(_make_report(48.77 + i * 0.001, 9.18))
    db_session.add(_make_report(49.0, 10.0))
    db_session.commit()
    reports = db_session.query(Report).all()
    run_clustering(reports, db_session)
    clustered = [r for r in reports if r.cluster_id is not None]
    noise = [r for r in reports if r.cluster_id is None]
    assert len(clustered) == 3
    assert len(noise) == 1


def test_cluster_ids_written_to_db(db_session):
    for i in range(3):
        db_session.add(_make_report(48.77 + i * 0.001, 9.18))
    db_session.commit()
    reports = db_session.query(Report).all()
    run_clustering(reports, db_session)
    # Query fresh from DB to verify persistence
    fresh = db_session.query(Report).all()
    assert all(r.cluster_id is not None for r in fresh)
    assert len(set(r.cluster_id for r in fresh)) == 1
