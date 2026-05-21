"""City Intelligence Score — composite metric from health, SLA, transparency, anomaly status."""

import time

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.analytics import compute_health_score
from app.anomaly import get_state
from app.config import CITIES, get_city
from app.database import get_db
from app.models import Report
from app.sla import SLA_TARGET_HOURS, get_params, survival
from app.transparency import compute_transparency

router = APIRouter()


def compute_intelligence_score(db: Session, city: str) -> dict:
    city_key, cfg = get_city(city)
    reports = db.query(Report).filter(Report.city == city_key).all()

    health = compute_health_score(reports)

    open_reports = [r for r in reports if r.status != "resolved"]
    probs = [1 - survival(SLA_TARGET_HOURS, *get_params(r.category, r.severity)) for r in open_reports]
    sla_score = (sum(probs) / len(probs) * 100) if probs else 100.0

    _, transparency_score = compute_transparency(reports)

    neighborhoods = cfg["neighborhoods"]
    now = time.time()
    active = sum(
        1 for *_, name in neighborhoods
        if (state := get_state(city_key, name)) and state["last_alert"] > 0
        and (now - state["last_alert"]) < 3600
    )
    anomaly_free = (1 - active / len(neighborhoods)) * 100

    composite = health * 0.30 + sla_score * 0.25 + transparency_score * 0.25 + anomaly_free * 0.20
    composite = round(max(0, min(100, composite)), 1)

    return {
        "city": city_key,
        "score": composite,
        "components": {
            "health": {"score": round(health, 1), "weight": 0.30},
            "sla_compliance": {"score": round(sla_score, 1), "weight": 0.25},
            "transparency": {"score": round(transparency_score, 1), "weight": 0.25},
            "anomaly_free": {"score": round(anomaly_free, 1), "weight": 0.20},
        },
    }


@router.get("/api/intelligence-score")
def intelligence_score(city: str = "stuttgart", db: Session = Depends(get_db)):
    return compute_intelligence_score(db, city)
