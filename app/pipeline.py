"""Pipeline Visualizer — on-the-fly pipeline status from report data."""

from fastapi import Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.anomaly import get_state
from app.config import SEVERITY_WEIGHTS, neighborhood_for_coords
from app.database import get_db
from app.models import Report

PIPELINE_STAGES = [
    {"name": "upload", "description": "Photo uploaded and stored"},
    {"name": "classification", "description": "AI categorization of issue type, severity, and department"},
    {"name": "anomaly_check", "description": "Bayesian anomaly detection for neighborhood activity"},
    {"name": "budget_impact", "description": "Report factored into LP budget optimization weights"},
    {"name": "dispatch_eligible", "description": "Eligibility for crew dispatch routing"},
]


def get_pipeline_status(report: Report) -> list[dict]:
    ts = report.created_at.isoformat() if report.created_at else None
    nh = neighborhood_for_coords(report.latitude, report.longitude, report.city)
    state = get_state(report.city, nh)
    nh_state = None
    if state:
        nh_state = {"alpha": state["alpha"], "beta": state["beta"],
                    "posterior_mean": round(state["alpha"] / state["beta"], 2)}

    dispatch_status = "skipped" if report.status == "resolved" else "completed"
    dispatch_details = {"status": report.status, "eligible": report.status == "open"}

    return [
        {"name": "upload", "status": "completed", "timestamp": ts,
         "details": {"photo_path": report.photo_path}},
        {"name": "classification", "timestamp": ts,
         "status": "completed" if report.category != "unclassified" else "skipped",
         "details": {"category": report.category, "severity": report.severity,
                     "department": report.department}},
        {"name": "anomaly_check", "status": "completed", "timestamp": ts,
         "details": {"checked": True, "neighborhood_state": nh_state}},
        {"name": "budget_impact", "status": "completed", "timestamp": ts,
         "details": {"department": report.department,
                     "severity_weight": SEVERITY_WEIGHTS[report.severity]}},
        {"name": "dispatch_eligible", "status": dispatch_status, "timestamp": ts,
         "details": dispatch_details},
    ]


def get_report_pipeline(report_id: int, db: Session = Depends(get_db)):
    report = db.query(Report).filter(Report.id == report_id).first()
    if not report:
        return JSONResponse(status_code=404, content={"error": "Report not found"})
    return {"report_id": report_id, "stages": get_pipeline_status(report)}


def get_pipeline_stages():
    return {"stages": PIPELINE_STAGES}
