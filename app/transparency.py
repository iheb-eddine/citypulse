"""Transparency Dashboard — department-level SLA compliance with exponential decay."""

import math
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Report
from app.sla import get_params, percentile, SLA_TARGET_HOURS

router = APIRouter()

DECAY_RATE = 0.05  # per day
GRADES = [(90, "A"), (80, "B"), (70, "C"), (60, "D")]


def _grade(score: float) -> str:
    for threshold, letter in GRADES:
        if score >= threshold:
            return letter
    return "F"


def compute_transparency(reports: list[Report], now: datetime | None = None) -> tuple[list, float]:
    """Returns (department_list, overall_score)."""
    now = now or datetime.now(timezone.utc)
    departments: dict[str, dict] = {}
    total_wc, total_wt = 0.0, 0.0

    for r in reports:
        created = r.created_at.replace(tzinfo=timezone.utc) if r.created_at.tzinfo is None else r.created_at
        age_days = max((now - created).total_seconds() / 86400, 0)
        weight = math.exp(-DECAY_RATE * age_days)
        scale, shape = get_params(r.category, r.severity)
        median_hours = percentile(0.5, scale, shape)

        if r.status == "resolved":
            compliant = 1
        else:
            compliant = 1 if age_days * 24 < SLA_TARGET_HOURS else 0

        dept = departments.setdefault(r.department, {
            "weighted_compliant": 0.0, "weighted_total": 0.0,
            "total": 0, "resolved": 0, "median_sum": 0.0,
        })
        dept["weighted_compliant"] += weight * compliant
        dept["weighted_total"] += weight
        dept["total"] += 1
        dept["resolved"] += 1 if r.status == "resolved" else 0
        dept["median_sum"] += median_hours
        total_wc += weight * compliant
        total_wt += weight

    result = []
    for name, d in departments.items():
        score = (d["weighted_compliant"] / d["weighted_total"] * 100) if d["weighted_total"] > 0 else 0
        result.append({
            "name": name, "score": round(score, 1),
            "total_reports": d["total"], "resolved_count": d["resolved"],
            "avg_resolution_hours": round(d["median_sum"] / d["total"], 1),
            "grade": _grade(score),
        })
    result.sort(key=lambda x: x["score"], reverse=True)
    overall = (total_wc / total_wt * 100) if total_wt > 0 else 0
    return result, overall


@router.get("/api/transparency")
def transparency_dashboard(city: str = "stuttgart", db: Session = Depends(get_db)):
    reports = db.query(Report).filter(Report.city == city).all()
    if not reports:
        return {"city": city, "overall_score": 0, "overall_grade": "F", "departments": []}
    departments, overall = compute_transparency(reports)
    return {"city": city, "overall_score": round(overall, 1), "overall_grade": _grade(overall), "departments": departments}
