"""CityPulse Health History — per-neighborhood daily health scores."""

from collections import Counter
from datetime import datetime, timedelta
from typing import Optional

import numpy as np
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.analytics import compute_health_score
from app.config import get_city, neighborhood_for_coords
from app.database import get_db
from app.models import Report

router = APIRouter()


@router.get("/api/health/history")
async def get_health_history(
    db: Session = Depends(get_db),
    city: Optional[str] = None,
    days: int = 30,
    neighborhood: Optional[str] = None,
):
    days = min(max(days, 1), 365)
    city_key, city_cfg = get_city(city)

    today = datetime.now().replace(hour=23, minute=59, second=59, microsecond=999999)
    start_date = (today - timedelta(days=days - 1)).replace(hour=0, minute=0, second=0, microsecond=0)

    reports = (
        db.query(Report)
        .filter(Report.city == city_key)
        .all()
    )

    # Assign neighborhoods, exclude non-neighborhood values
    city_name = city_cfg["name"]
    exclude = {city_name, "Unknown area"}
    nh_reports: dict[str, list] = {}
    for r in reports:
        nh = neighborhood_for_coords(r.latitude, r.longitude, city_key)
        if nh not in exclude:
            nh_reports.setdefault(nh, []).append(r)

    # Filter by neighborhood param
    if neighborhood:
        nh_reports = {k: v for k, v in nh_reports.items() if k == neighborhood}

    # Build per-neighborhood history
    neighborhoods = []
    for name, reps in sorted(nh_reports.items()):
        history = []
        for i in range(days):
            current_day = start_date + timedelta(days=i)
            end_of_day = current_day.replace(hour=23, minute=59, second=59, microsecond=999999)
            start_of_day = current_day.replace(hour=0, minute=0, second=0, microsecond=0)

            cumulative = [r for r in reps if r.created_at <= end_of_day]
            new_today = [r for r in reps if start_of_day <= r.created_at <= end_of_day]

            cats = Counter(r.category for r in new_today)
            top_cat = cats.most_common(1)[0][0] if cats else None

            history.append({
                "date": current_day.strftime("%Y-%m-%d"),
                "health_score": round(compute_health_score(cumulative), 1),
                "report_count": len(new_today),
                "top_category": top_cat,
            })
        neighborhoods.append({"name": name, "history": history})

    return {"city": city_key, "days": days, "neighborhoods": neighborhoods}


@router.get("/api/health/forecast")
async def get_health_forecast(
    db: Session = Depends(get_db),
    city: Optional[str] = None,
    history_days: int = 14,
    forecast_days: int = 7,
):
    history_days = min(max(history_days, 2), 90)
    forecast_days = min(max(forecast_days, 1), 30)
    city_key, _ = get_city(city)

    today = datetime.now().replace(hour=23, minute=59, second=59, microsecond=999999)
    reports = db.query(Report).filter(Report.city == city_key).all()

    scores = []
    for i in range(history_days):
        end = (today - timedelta(days=history_days - 1 - i)).replace(hour=23, minute=59, second=59)
        cumulative = [r for r in reports if r.created_at <= end]
        scores.append(compute_health_score(cumulative))

    x = np.arange(history_days, dtype=float)
    slope, intercept = np.polyfit(x, scores, 1)

    trend = "improving" if slope > 0.5 else ("declining" if slope < -0.5 else "stable")
    current_score = round(scores[-1], 1)

    forecast = []
    for d in range(1, forecast_days + 1):
        pred = slope * (history_days - 1 + d) + intercept
        pred = round(min(max(pred, 0), 100), 1)
        date_str = (datetime.now() + timedelta(days=d)).strftime("%Y-%m-%d")
        forecast.append({"day": d, "date": date_str, "predicted_score": pred})

    return {
        "city": city_key,
        "trend": trend,
        "slope": round(float(slope), 4),
        "current_score": current_score,
        "forecast": forecast,
    }
