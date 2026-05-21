"""Tests for Work Order Generator."""
import pytest
from app.workorders import topological_sort, _get_ancestors, _critical_path, DEPENDENCIES, SLA_HOURS


class TestGetAncestors:
    def test_roads_has_water_and_electrical(self):
        assert _get_ancestors("roads") == {"water", "electrical"}

    def test_parks_has_sanitation(self):
        assert _get_ancestors("parks") == {"sanitation"}

    def test_water_has_no_ancestors(self):
        assert _get_ancestors("water") == set()

    def test_general_has_no_ancestors(self):
        assert _get_ancestors("general") == set()


class TestTopologicalSort:
    def test_single_department(self):
        assert topological_sort({"water"}) == [["water"]]

    def test_water_roads(self):
        levels = topological_sort({"water", "roads"})
        assert levels == [["water"], ["roads"]]

    def test_parallel_prerequisites(self):
        levels = topological_sort({"water", "electrical", "roads"})
        assert len(levels) == 2
        assert set(levels[0]) == {"water", "electrical"}
        assert levels[1] == ["roads"]

    def test_cycle_detection(self):
        import app.workorders as wo
        original = wo.DEPENDENCIES.copy()
        wo.DEPENDENCIES["roads"] = ["water"]
        try:
            with pytest.raises(ValueError, match="Cycle detected"):
                topological_sort({"water", "roads"})
        finally:
            wo.DEPENDENCIES.clear()
            wo.DEPENDENCIES.update(original)

    def test_independent_departments(self):
        levels = topological_sort({"water", "sanitation"})
        assert len(levels) == 1
        assert set(levels[0]) == {"water", "sanitation"}


class TestCriticalPath:
    def test_roads_critical_path(self):
        path, hours = _critical_path({"water", "electrical", "roads"})
        assert path == ["water", "roads"]
        assert hours == 72  # 24 + 48

    def test_single_dept(self):
        path, hours = _critical_path({"general"})
        assert path == ["general"]
        assert hours == 24

    def test_parks_path(self):
        path, hours = _critical_path({"sanitation", "parks"})
        assert path == ["sanitation", "parks"]
        assert hours == 48  # 12 + 36


class TestWorkorderEndpoint:
    def test_workorder_roads_report(self, test_client, db_session):
        from app.models import Report
        r = Report(photo_path="x.jpg", latitude=48.7, longitude=9.1, city="stuttgart",
                   category="pothole", severity="high", department="roads", description="test")
        db_session.add(r)
        db_session.commit()
        resp = test_client.get(f"/api/reports/{r.id}/workorder")
        assert resp.status_code == 200
        data = resp.json()
        assert set(data["departments"]) == {"water", "electrical", "roads"}
        assert data["steps"][0]["order"] == 1
        assert data["steps"][-1]["department"] == "roads"
        assert data["total_estimated_hours"] == 90  # 24 + 18 + 48
        assert data["critical_path"] == ["water", "roads"]
        assert data["critical_path_hours"] == 72

    def test_workorder_single_dept(self, test_client, db_session):
        from app.models import Report
        r = Report(photo_path="x.jpg", latitude=48.7, longitude=9.1, city="stuttgart",
                   category="flooding", severity="medium", department="water", description="test")
        db_session.add(r)
        db_session.commit()
        resp = test_client.get(f"/api/reports/{r.id}/workorder")
        assert resp.status_code == 200
        data = resp.json()
        assert data["departments"] == ["water"]
        assert len(data["steps"]) == 1
        assert data["steps"][0]["depends_on"] == []

    def test_workorder_not_found(self, test_client):
        resp = test_client.get("/api/reports/9999/workorder")
        assert resp.status_code == 404

    def test_dependencies_endpoint(self, test_client):
        resp = test_client.get("/api/workorders/dependencies")
        assert resp.status_code == 200
        data = resp.json()
        assert data["dependencies"] == DEPENDENCIES
        assert data["sla_hours"] == SLA_HOURS
