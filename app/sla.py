"""SLA Survival Prediction — Weibull survival analysis for report resolution."""

import math
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Report

router = APIRouter()

WEIBULL_PARAMS = {
    "pothole":     {"low": (168, 1.4), "medium": (120, 1.5), "high": (72, 1.7), "critical": (36, 2.0)},
    "streetlight": {"low": (96, 1.5),  "medium": (72, 1.5),  "high": (36, 1.8), "critical": (18, 2.2)},
    "graffiti":    {"low": (96, 1.3),  "medium": (72, 1.4),  "high": (48, 1.6), "critical": (24, 1.8)},
    "flooding":    {"low": (120, 1.5), "medium": (96, 1.5),  "high": (48, 1.8), "critical": (24, 2.0)},
}
_DEFAULT = {"low": (144, 1.4), "medium": (96, 1.5), "high": (48, 1.7), "critical": (24, 2.0)}

SLA_TARGET_HOURS = 48


def get_params(category: str, severity: str) -> tuple[float, float]:
    return WEIBULL_PARAMS.get(category, _DEFAULT).get(severity, _DEFAULT["medium"])


def survival(t: float, scale: float, shape: float) -> float:
    """S(t) = exp(-(t/λ)^k)"""
    return math.exp(-((t / scale) ** shape))


def percentile(p: float, scale: float, shape: float) -> float:
    """Time by which fraction p of reports are resolved."""
    return scale * ((-math.log(1 - p)) ** (1 / shape))


@router.get("/api/reports/{report_id}/sla")
def report_sla(report_id: int, db: Session = Depends(get_db)):
    report = db.query(Report).filter(Report.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    scale, shape = get_params(report.category, report.severity)
    median = percentile(0.5, scale, shape)
    p75 = percentile(0.75, scale, shape)
    p90 = percentile(0.90, scale, shape)
    t_max = 2 * median
    curve = [{"t": round(t_max * i / 9, 1), "survival": round(survival(t_max * i / 9, scale, shape), 4)}
             for i in range(10)]
    return {"report_id": report_id, "category": report.category, "severity": report.severity,
            "scale": scale, "shape": shape,
            "median_hours": round(median, 1), "p75_hours": round(p75, 1), "p90_hours": round(p90, 1),
            "survival_curve": curve}


@router.get("/api/sla/summary")
def sla_summary(city: str = "stuttgart", db: Session = Depends(get_db)):
    reports = db.query(Report).filter(Report.city == city, Report.status != "resolved").all()
    if not reports:
        return {"city": city, "open_reports": 0, "overall_compliance": 1.0, "by_category": {},
                "compliance_rate": 1.0, "total_open": 0, "on_track": 0, "at_risk": 0, "overdue": 0}
    by_cat: dict[str, list[float]] = {}
    on_track = at_risk = overdue = 0
    for r in reports:
        scale, shape = get_params(r.category, r.severity)
        prob_resolved = 1 - survival(SLA_TARGET_HOURS, scale, shape)
        by_cat.setdefault(r.category, []).append(prob_resolved)
        if prob_resolved >= 0.7:
            on_track += 1
        elif prob_resolved >= 0.3:
            at_risk += 1
        else:
            overdue += 1
    cat_compliance = {cat: round(sum(v) / len(v), 4) for cat, v in by_cat.items()}
    all_probs = [p for v in by_cat.values() for p in v]
    overall = round(sum(all_probs) / len(all_probs), 4)
    return {"city": city, "open_reports": len(reports), "target_hours": SLA_TARGET_HOURS,
            "overall_compliance": overall, "by_category": cat_compliance,
            "compliance_rate": overall, "total_open": len(reports),
            "on_track": on_track, "at_risk": at_risk, "overdue": overdue}
