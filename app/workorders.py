"""Work Order Generator — Kahn's algorithm for multi-department coordination."""
from collections import deque
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Report

router = APIRouter()

DEPENDENCIES = {"water": ["roads"], "electrical": ["roads"], "sanitation": ["parks"]}
SLA_HOURS = {"water": 24, "electrical": 18, "roads": 48, "sanitation": 12, "parks": 36, "general": 24}


def _get_ancestors(dept: str) -> set[str]:
    ancestors, queue = set(), deque([dept])
    while queue:
        node = queue.popleft()
        for src, targets in DEPENDENCIES.items():
            if node in targets and src not in ancestors:
                ancestors.add(src)
                queue.append(src)
    return ancestors


def topological_sort(departments: set[str]) -> list[list[str]]:
    """Kahn's algorithm returning levels (parallel batches). Raises ValueError on cycle."""
    in_degree = {d: 0 for d in departments}
    adj: dict[str, list[str]] = {d: [] for d in departments}
    for src in departments:
        for tgt in DEPENDENCIES.get(src, []):
            if tgt in departments:
                adj[src].append(tgt)
                in_degree[tgt] += 1
    levels, queue, processed = [], deque(d for d, deg in in_degree.items() if deg == 0), 0
    while queue:
        level = list(queue)
        levels.append(level)
        queue = deque()
        for node in level:
            processed += 1
            for nb in adj[node]:
                in_degree[nb] -= 1
                if in_degree[nb] == 0:
                    queue.append(nb)
    if processed < len(departments):
        raise ValueError("Cycle detected in dependency graph")
    return levels


def _critical_path(departments: set[str]) -> tuple[list[str], int]:
    levels = topological_sort(departments)
    best: dict[str, tuple[int, str | None]] = {d: (SLA_HOURS.get(d, 24), None) for d in departments}
    for level in levels:
        for node in level:
            for tgt in DEPENDENCIES.get(node, []):
                if tgt in departments:
                    new = best[node][0] + SLA_HOURS.get(tgt, 24)
                    if new > best[tgt][0]:
                        best[tgt] = (new, node)
    end = max(departments, key=lambda d: best[d][0])
    path, cur = [], end
    while cur is not None:
        path.append(cur)
        cur = best[cur][1]
    path.reverse()
    return path, best[end][0]


@router.get("/api/reports/{report_id}/workorder")
def generate_workorder(report_id: int, db: Session = Depends(get_db)):
    report = db.query(Report).filter(Report.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    all_depts = _get_ancestors(report.department) | {report.department}
    try:
        levels = topological_sort(all_depts)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    steps, order = [], 1
    for level in levels:
        for d in sorted(level):
            deps_on = sorted(s for s in all_depts if d in DEPENDENCIES.get(s, []))
            steps.append({"order": order, "department": d,
                          "estimated_hours": SLA_HOURS.get(d, 24), "depends_on": deps_on})
        order += 1
    crit_path, crit_hours = _critical_path(all_depts)
    return {"report_id": report_id, "departments": sorted(all_depts), "steps": steps,
            "total_estimated_hours": sum(SLA_HOURS.get(d, 24) for d in all_depts),
            "critical_path": crit_path, "critical_path_hours": crit_hours}


@router.get("/api/workorders/dependencies")
def get_dependencies():
    return {"dependencies": DEPENDENCIES, "sla_hours": SLA_HOURS}
