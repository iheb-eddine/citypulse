"""CityPulse Time-Lapse Simulation — daily snapshots of report evolution."""

from collections import Counter
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.analytics import compute_health_score
from app.config import get_city
from app.database import get_db
from app.models import Report

router = APIRouter()


@router.get("/api/timelapse")
async def get_timelapse(
    db: Session = Depends(get_db),
    city: Optional[str] = None,
    days: int = 30,
):
    days = min(max(days, 1), 365)
    city_key, _ = get_city(city)
    reports = db.query(Report).filter(Report.city == city_key).all()

    today = datetime.now().replace(hour=23, minute=59, second=59, microsecond=999999)
    start_date = (today - timedelta(days=days - 1)).replace(hour=0, minute=0, second=0, microsecond=0)

    snapshots = []
    for i in range(days):
        current_day = start_date + timedelta(days=i)
        end_of_day = current_day.replace(hour=23, minute=59, second=59, microsecond=999999)
        start_of_day = current_day.replace(hour=0, minute=0, second=0, microsecond=0)

        cumulative = [r for r in reports if r.created_at <= end_of_day]
        new_today = [r for r in cumulative if r.created_at >= start_of_day]

        snapshots.append({
            "day": i + 1,
            "date": current_day.strftime("%Y-%m-%d"),
            "report_count": len(cumulative),
            "health_score": round(compute_health_score(cumulative), 1),
            "categories": dict(Counter(r.category for r in cumulative)),
            "severity_distribution": dict(Counter(r.severity for r in cumulative)),
            "new_reports_today": len(new_today),
        })

    return snapshots
