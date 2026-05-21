"""Priority Scoring Engine — composite priority score for dispatch ordering."""

import time
from datetime import datetime, timezone
from math import exp, log

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.config import SEVERITY_WEIGHTS, neighborhood_for_coords
from app.database import get_db
from app.models import Report
from app import anomaly, sla

router = APIRouter()

WEIGHTS = {"severity": 0.30, "age": 0.20, "confirmations": 0.15, "anomaly": 0.15, "sla_risk": 0.20}
AGE_HALF_LIFE = 168
CONFIRMATION_CAP = 10
ANOMALY_PRIORITY_WINDOW = 3600


def compute_priority(report: Report, city: str, now: datetime | None = None) -> dict:
    if now is None:
        now = datetime.now(timezone.utc)
    age_hours = max(0.0, (now - report.created_at.replace(tzinfo=timezone.utc)).total_seconds() / 3600)

    severity_norm = SEVERITY_WEIGHTS[report.severity] / max(SEVERITY_WEIGHTS.values())
    age_factor = min(1.0, 1 - exp(-age_hours / AGE_HALF_LIFE))
    confirmations = max(0, report.confirmations)
    confirm_factor = min(1.0, log(1 + confirmations) / log(1 + CONFIRMATION_CAP))

    neighborhood = neighborhood_for_coords(report.latitude, report.longitude, city)
    state = anomaly.get_state(city, neighborhood)
    if state and state["last_alert"] > 0:
        elapsed = time.time() - state["last_alert"]
        anomaly_factor = 1.0 if elapsed < ANOMALY_PRIORITY_WINDOW else 0.0
    else:
        anomaly_factor = 0.0

    scale, shape = sla.get_params(report.category, report.severity)
    sla_risk = 1.0 - sla.survival(age_hours, scale, shape)

    factors = {"severity": severity_norm, "age": age_factor, "confirmations": confirm_factor,
               "anomaly": anomaly_factor, "sla_risk": sla_risk}
    score = max(0.0, min(100.0, 100 * sum(WEIGHTS[k] * factors[k] for k in WEIGHTS)))

    return {"report_id": report.id, "score": round(score, 1), "factors": factors, "weights": WEIGHTS}


def compute_priorities(reports: list[Report], city: str) -> list[dict]:
    results = [compute_priority(r, city) for r in reports]
    results.sort(key=lambda x: x["score"], reverse=True)
    return results


@router.get("/api/reports/priority")
def reports_priority(city: str = "stuttgart", db: Session = Depends(get_db)):
    reports = db.query(Report).filter(Report.city == city, Report.status != "resolved").all()
    priorities = compute_priorities(reports, city)
    enriched = []
    for p in priorities:
        r = next(r for r in reports if r.id == p["report_id"])
        enriched.append({**p, "category": r.category, "severity": r.severity,
                         "status": r.status, "neighborhood": neighborhood_for_coords(r.latitude, r.longitude, city),
                         "created_at": r.created_at.isoformat()})
    return {"city": city, "total": len(enriched), "reports": enriched}


@router.get("/api/reports/{report_id}/priority")
def report_priority(report_id: int, db: Session = Depends(get_db)):
    report = db.query(Report).filter(Report.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    city = report.city or "stuttgart"
    p = compute_priority(report, city)
    return {**p, "category": report.category, "severity": report.severity,
            "status": report.status, "neighborhood": neighborhood_for_coords(report.latitude, report.longitude, city),
            "created_at": report.created_at.isoformat()}
