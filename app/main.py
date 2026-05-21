"""CityPulse FastAPI application — routes, templates, static files."""

import asyncio
import json as _json
from collections import Counter
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from uuid import uuid4

import folium
from folium.plugins import HeatMap, Fullscreen
from fastapi import Depends, FastAPI, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import inspect as sa_inspect, text
from sqlalchemy.orm import Session

import httpx
import os

from dotenv import load_dotenv

from io import BytesIO as _BytesIO
from PIL import Image

from app.database import create_tables, get_db
from app.classifier import classify_image, FALLBACK
from app.models import Report
from app.news import fetch_news
from app.config import (
    SEVERITY_COLORS, SEVERITY_WEIGHTS,
    CITIES, DEFAULT_CITY, VALID_CATEGORIES, VALID_SEVERITIES,
    VALID_STATUSES, SEVERITY_ESCALATION, MAX_FILE_SIZE,
    get_city, nearest_city, neighborhood_for_coords,
)

from app.analytics import (
    estimate_resolution_days, compute_health_score, compute_trend,
    compute_category_breakdown, compute_severity_breakdown,
    compute_accessibility_score, compute_top_accessibility_categories,
    compute_risk_scores, compute_hotspots, run_clustering,
)

from app.observability import (
    ObservabilityMiddleware, health_check, get_metrics, setup_logging,
)
from app.anomaly import check_anomaly, get_state as anomaly_get_state
from app.budget import optimize_budget
from app.dispatch import optimize_dispatch
from app.pipeline import get_report_pipeline, get_pipeline_stages, get_pipeline_status
from app.priority import compute_priority
from app.sla import get_params as sla_params, percentile as sla_percentile
from app.severity_reasoning import generate_reasoning
from app.sensors import router as sensors_router, sensor_loop
from app.timelapse import router as timelapse_router
from app.diffusion import compute_diffusion
from app.causality import compute_causality
from app.phash import find_duplicates, find_similarity_clusters
from app.sla import router as sla_router
from app.workorders import router as workorders_router
from app.transparency import router as transparency_router
from app.priority import router as priority_router
from app.health_history import router as health_history_router
from app.intelligence import router as intelligence_router

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "static" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


# --- SSE live updates ---
sse_clients: set[asyncio.Queue] = set()


def notify_sse_clients(event_data: dict) -> None:
    """Push event to all connected SSE clients. Drop slow/dead clients."""
    payload = _json.dumps(event_data)
    dead: list[asyncio.Queue] = []
    for q in sse_clients:
        try:
            q.put_nowait(payload)
        except asyncio.QueueFull:
            dead.append(q)
    for q in dead:
        sse_clients.discard(q)

# Magic bytes → file extension
MAGIC_JPEG = b"\xff\xd8\xff"
MAGIC_PNG = b"\x89PNG"
MAGIC_RIFF = b"RIFF"
MAGIC_WEBP = b"WEBP"


def detect_file_type(data: bytes) -> Optional[str]:
    """Return file extension from magic bytes, or None if unrecognized."""
    if data[:3] == MAGIC_JPEG:
        return ".jpg"
    if data[:4] == MAGIC_PNG:
        return ".png"
    if data[:4] == MAGIC_RIFF and data[8:12] == MAGIC_WEBP:
        return ".webp"
    return None


EXT_TO_FORMAT = {".jpg": "JPEG", ".png": "PNG", ".webp": "WEBP"}


def strip_metadata(data: bytes, ext: str) -> bytes:
    """Strip all metadata by copying pixel data to a fresh image."""
    try:
        img = Image.open(_BytesIO(data))
        clean = Image.new(img.mode, img.size)
        clean.paste(img)
        buf = _BytesIO()
        clean.save(buf, format=EXT_TO_FORMAT[ext])
        return buf.getvalue()
    except Exception:
        return data


def _error(code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=422, content={"error": {"code": code, "message": message}})


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    create_tables()
    # Migrate: add confirmations column if missing (existing DBs)
    from app.database import engine
    with engine.connect() as conn:
        cols = [c["name"] for c in sa_inspect(engine).get_columns("reports")]
        if "confirmations" not in cols:
            conn.execute(text("ALTER TABLE reports ADD COLUMN confirmations INTEGER NOT NULL DEFAULT 0"))
            conn.commit()
        if "status" not in cols:
            conn.execute(text("ALTER TABLE reports ADD COLUMN status TEXT NOT NULL DEFAULT 'open'"))
            conn.commit()
        if "city" not in cols:
            conn.execute(text("ALTER TABLE reports ADD COLUMN city TEXT NOT NULL DEFAULT 'stuttgart'"))
            conn.execute(text("UPDATE reports SET city = 'stuttgart' WHERE city IS NULL"))
            conn.commit()
    _sensor_task = asyncio.create_task(sensor_loop())
    yield
    _sensor_task.cancel()


app = FastAPI(lifespan=lifespan)
app.add_middleware(ObservabilityMiddleware)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")
app.get("/health")(health_check)
app.get("/metrics")(get_metrics)
app.get("/api/reports/{report_id}/pipeline")(get_report_pipeline)
app.get("/api/pipeline/stages")(get_pipeline_stages)
app.include_router(sensors_router)
app.include_router(timelapse_router)
app.include_router(sla_router)
app.include_router(workorders_router)
app.include_router(transparency_router)
app.include_router(priority_router)
app.include_router(health_history_router)
app.include_router(intelligence_router)


@app.get("/api/stream")
async def sse_stream():
    q: asyncio.Queue = asyncio.Queue(maxsize=64)
    sse_clients.add(q)

    async def event_generator():
        try:
            while True:
                data = await q.get()
                yield f"data: {data}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            sse_clients.discard(q)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/submit")
async def submit_page(request: Request, city: Optional[str] = None):
    city_key, _ = get_city(city)
    return templates.TemplateResponse(request, "submit.html", {"city": city_key, "cities": CITIES})




def _build_dashboard_data(db: Session, category: Optional[str] = None, severity: Optional[str] = None, city: Optional[str] = None):
    """Shared logic for dashboard HTML and API."""
    city_key, city_cfg = get_city(city)
    all_reports = db.query(Report).filter(Report.city == city_key).all()
    run_clustering(all_reports, db, city_key)

    # Filter after clustering so cluster_ids stay consistent
    reports = all_reports
    if category and category in VALID_CATEGORIES:
        reports = [r for r in reports if r.category == category]
    if severity and severity in VALID_SEVERITIES:
        reports = [r for r in reports if r.severity == severity]

    health_score = compute_health_score(reports)
    trend = compute_trend(reports)
    categories = compute_category_breakdown(reports)
    severities = compute_severity_breakdown(reports)
    hotspots = compute_hotspots(reports, city_key)
    risk_scores = compute_risk_scores(reports, city_key)
    total = len(reports)
    statuses = dict(Counter(r.status for r in reports))
    accessibility_score = compute_accessibility_score(reports)
    top_accessibility_categories = compute_top_accessibility_categories(reports)

    if trend > 0:
        trend_text = f"↑ {trend} more reports this week"
    elif trend < 0:
        trend_text = f"↓ {abs(trend)} fewer reports this week"
    else:
        trend_text = "→ Same as last week"

    return reports, {
        "health_score": health_score, "total_reports": total,
        "categories": categories, "severities": severities,
        "hotspots": hotspots, "risk_scores": risk_scores, "trend_text": trend_text, "trend": trend,
        "statuses": statuses,
        "accessibility_score": accessibility_score,
        "top_accessibility_categories": top_accessibility_categories,
        "city_key": city_key, "city_cfg": city_cfg,
    }


@app.get("/")
async def landing(request: Request):
    return templates.TemplateResponse(request, "landing.html", {})


@app.get("/dashboard")
async def dashboard(
    request: Request, db: Session = Depends(get_db),
    category: Optional[str] = None, severity: Optional[str] = None,
    city: Optional[str] = None,
):
    reports, stats = _build_dashboard_data(db, category, severity, city)
    city_cfg = stats["city_cfg"]
    city_key = stats["city_key"]
    m = folium.Map(location=[city_cfg["lat"], city_cfg["lng"]], zoom_start=city_cfg["zoom"])
    Fullscreen().add_to(m)
    SEV_BADGE = {"low": "#43a047", "medium": "#fb8c00", "high": "#f4511e", "critical": "#c62828"}
    STATUS_LABEL = {"open": "Open", "in_progress": "In Progress", "resolved": "Resolved"}
    bounds = []
    marker_group = folium.FeatureGroup(name="Reports")
    for r in reports:
        sev_color = SEV_BADGE.get(r.severity, "#1a73e8")
        status_label = STATUS_LABEL.get(r.status, "Open")
        status_btns = ''.join(
            f'<button onclick="(function(btn){{'
            f'fetch((parent.location.origin||location.origin)+&quot;/api/reports/{r.id}/status&quot;,'
            f'{{method:&quot;PATCH&quot;,headers:{{&quot;Content-Type&quot;:&quot;application/json&quot;}},'
            f'body:JSON.stringify({{status:&quot;{s}&quot;}})}})'
            f'.then(function(r){{return r.json()}})'
            f'.then(function(d){{btn.parentElement.previousElementSibling.textContent=&quot;Status: {STATUS_LABEL[s]}&quot;}})'
            f'}})(this)" '
            f'style="margin:2px;padding:2px 8px;border:1px solid #ccc;border-radius:4px;background:#f5f5f5;cursor:pointer;font-size:11px">'
            f'{STATUS_LABEL[s]}</button>'
            for s in ("open", "in_progress", "resolved")
        )
        popup_html = (
            f'<div style="font-family:-apple-system,BlinkMacSystemFont,sans-serif;min-width:160px">'
            f'<img src="{r.photo_path}" width="160" style="border-radius:6px;display:block;margin-bottom:6px">'
            f'<div style="font-weight:700;font-size:13px;margin-bottom:4px;text-transform:capitalize">{r.category}</div>'
            f'<span style="display:inline-block;background:{sev_color};color:#fff;padding:1px 8px;border-radius:10px;font-size:11px;font-weight:600;text-transform:uppercase">{r.severity}</span>'
            f'<div style="color:#5f6b7a;font-size:11px;margin-top:6px">{r.department}<br>{r.created_at}</div>'
            f'<div style="font-size:11px;margin-top:4px;font-weight:600">Status: {status_label}</div>'
            f'<div style="color:#1a73e8;font-size:11px;margin-top:4px">Estimated resolution: ~{estimate_resolution_days(r.category, r.severity)} days</div>'
            f'<div style="margin-top:4px">{status_btns}</div>'
            f'<button id="confirm-btn-{r.id}" onclick="(function(btn){{'
            f'btn.disabled=true;'
            f'fetch((parent.location.origin||location.origin)+&quot;/api/reports/{r.id}/confirm&quot;,{{method:&quot;POST&quot;}})'
            f'.then(function(r){{return r.json()}})'
            f'.then(function(d){{'
            f'btn.textContent=&quot;\\U0001f44d Confirm (&quot;+d.confirmations+&quot;)&quot;;'
            f'btn.disabled=false;'
            f'var sev=btn.previousElementSibling.previousElementSibling.previousElementSibling.previousElementSibling;'
            f'if(sev)sev.textContent=d.severity;'
            f'}})'
            f'.catch(function(){{btn.disabled=false}})'
            f'}})(this)" '
            f'style="margin-top:6px;width:100%;padding:4px 0;border:1px solid #ccc;border-radius:6px;background:#f5f5f5;cursor:pointer;font-size:12px">'
            f'\U0001f44d Confirm ({r.confirmations})</button>'
            f'</div>'
        )
        icon_color = "gray" if r.status == "resolved" else SEVERITY_COLORS.get(r.severity, "blue")
        folium.Marker(
            location=[r.latitude, r.longitude],
            popup=folium.Popup(popup_html, max_width=220),
            icon=folium.Icon(color=icon_color),
        ).add_to(marker_group)
        bounds.append([r.latitude, r.longitude])
    marker_group.add_to(m)
    if reports:
        heat_data = [[r.latitude, r.longitude, SEVERITY_WEIGHTS.get(r.severity, 1) / 5] for r in reports]
        HeatMap(heat_data, name="Heatmap", radius=25, min_opacity=0.4, max_opacity=0.8).add_to(m)
    # Risk zone overlays
    if stats["risk_scores"]:
        risk_group = folium.FeatureGroup(name="Risk Zones")
        for rs in stats["risk_scores"]:
            folium.CircleMarker(
                location=[rs["lat"], rs["lng"]], radius=35, color=rs["color"],
                fill=True, fill_color=rs["color"], fill_opacity=0.3, weight=3,
                tooltip=f"{rs['name']}: {rs.get('grade','?')} — Risk {rs['risk_score']}",
            ).add_to(risk_group)
        risk_group.add_to(m)
    folium.LayerControl().add_to(m)
    if bounds:
        m.fit_bounds(bounds, padding=[20, 20])
    map_html = m._repr_html_()
    return templates.TemplateResponse(
        request, "dashboard.html",
        {
            "map_html": map_html, "empty": stats["total_reports"] == 0,
            **stats,
            "filter_category": category or "",
            "filter_severity": severity or "",
            "city": city_key,
            "cities": CITIES,
        },
    )


@app.get("/api/dashboard")
async def api_dashboard(
    db: Session = Depends(get_db),
    category: Optional[str] = None, severity: Optional[str] = None,
    city: Optional[str] = None,
):
    reports, stats = _build_dashboard_data(db, category, severity, city)
    return {
        **stats,
        "reports": [
            {
                "id": r.id, "photo_path": r.photo_path,
                "latitude": r.latitude, "longitude": r.longitude,
                "category": r.category, "severity": r.severity,
                "department": r.department, "description": r.description,
                "cluster_id": r.cluster_id, "created_at": str(r.created_at),
                "confirmations": r.confirmations, "status": r.status,
            }
            for r in reports
        ],
    }


@app.get("/api/reports")
async def get_reports(db: Session = Depends(get_db), city: Optional[str] = None):
    city_key, _ = get_city(city)
    reports = db.query(Report).filter(Report.city == city_key).order_by(Report.created_at.desc()).all()
    return [
        {
            "id": r.id, "photo_path": r.photo_path,
            "latitude": r.latitude, "longitude": r.longitude,
            "category": r.category, "severity": r.severity,
            "department": r.department, "description": r.description,
            "cluster_id": r.cluster_id, "created_at": str(r.created_at),
            "confirmations": r.confirmations, "status": r.status,
        }
        for r in reports
    ]


@app.get("/api/reports/geojson")
async def get_reports_geojson(db: Session = Depends(get_db), city: Optional[str] = None):
    city_key, _ = get_city(city)
    reports = db.query(Report).filter(Report.city == city_key).order_by(Report.created_at.desc()).all()
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [r.longitude, r.latitude]},
                "properties": {
                    "id": r.id, "photo_path": r.photo_path,
                    "category": r.category, "severity": r.severity,
                    "department": r.department, "description": r.description,
                    "status": r.status, "confirmations": r.confirmations,
                    "cluster_id": r.cluster_id, "created_at": str(r.created_at),
                },
            }
            for r in reports
        ],
    }


@app.post("/api/reports")
async def create_report(
    photo: Optional[UploadFile] = File(None),
    latitude: Optional[str] = Form(None),
    longitude: Optional[str] = Form(None),
    description_text: Optional[str] = Form(None),
    city: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    # 1. File presence
    if photo is None or photo.filename == "":
        return _error("MISSING_FILE", "A photo file is required")

    # 2. Read content
    content = await photo.read()

    # 3. Empty check
    if len(content) == 0:
        return _error("EMPTY_FILE", "Uploaded file is empty")

    # 4. Size check
    if len(content) > MAX_FILE_SIZE:
        return _error("FILE_TOO_LARGE", "File exceeds 10MB limit")

    # 5. Type check
    ext = detect_file_type(content)
    if ext is None:
        return _error("INVALID_FILE_TYPE", "File must be JPEG, PNG, or WebP")

    # 5b. Strip EXIF / metadata
    content = strip_metadata(content, ext)

    # 6. Latitude validation
    if latitude is None:
        return _error("INVALID_LATITUDE", "Latitude is required")
    try:
        lat = float(latitude)
    except (ValueError, TypeError):
        return _error("INVALID_LATITUDE", "Latitude must be a valid number")
    if lat < -90 or lat > 90:
        return _error("INVALID_LATITUDE", "Latitude must be between -90 and 90")

    # 7. Longitude validation
    if longitude is None:
        return _error("INVALID_LONGITUDE", "Longitude is required")
    try:
        lng = float(longitude)
    except (ValueError, TypeError):
        return _error("INVALID_LONGITUDE", "Longitude must be a valid number")
    if lng < -180 or lng > 180:
        return _error("INVALID_LONGITUDE", "Longitude must be between -180 and 180")

    # 8. Save file
    filename = f"{uuid4()}{ext}"
    filepath = UPLOAD_DIR / filename
    filepath.write_bytes(content)

    # 9. Classify image via AI (falls back automatically on any failure)
    result = await classify_image(content)

    # 9b. Merge citizen voice description if provided
    if description_text and description_text.strip():
        result["description"] = f"AI: {result['description']} | Citizen: {description_text.strip()}"

    # 10. Resolve city
    report_city = city if city in CITIES else nearest_city(lat, lng)

    # 11. Create report
    report = Report(
        photo_path=f"/static/uploads/{filename}",
        latitude=lat,
        longitude=lng,
        city=report_city,
        **result,
    )
    db.add(report)
    db.commit()
    db.refresh(report)

    # Notify SSE clients
    notify_sse_clients({
        "id": report.id,
        "category": report.category,
        "severity": report.severity,
        "neighborhood": neighborhood_for_coords(report.latitude, report.longitude, report.city),
        "city": report.city,
    })

    try:
        check_anomaly(report.city, neighborhood_for_coords(report.latitude, report.longitude, report.city))
    except Exception:
        pass

    # Duplicate detection: nearby similar reports
    cutoff = datetime.now() - timedelta(days=7)
    nearby = db.query(Report).filter(
        Report.id != report.id,
        Report.category == report.category,
        Report.latitude.between(report.latitude - 0.002, report.latitude + 0.002),
        Report.longitude.between(report.longitude - 0.002, report.longitude + 0.002),
        Report.created_at >= cutoff,
    ).all()

    resp = {
        "id": report.id,
        "photo_path": report.photo_path,
        "latitude": report.latitude,
        "longitude": report.longitude,
        "category": report.category,
        "severity": report.severity,
        "department": report.department,
        "description": report.description,
        "status": report.status,
        "created_at": str(report.created_at),
        "estimated_resolution_days": estimate_resolution_days(report.category, report.severity),
    }
    if nearby:
        resp["nearby_similar"] = [{"id": r.id, "description": r.description} for r in nearby]

    # 11. Return 201
    return JSONResponse(status_code=201, content=resp)




@app.post("/api/reports/{report_id}/confirm")
async def confirm_report(report_id: int, db: Session = Depends(get_db)):
    report = db.query(Report).filter(Report.id == report_id).first()
    if not report:
        return JSONResponse(status_code=404, content={"error": "Report not found"})
    report.confirmations = Report.confirmations + 1
    db.flush()
    db.refresh(report)
    if report.confirmations == 3:
        report.severity = SEVERITY_ESCALATION[report.severity]
    db.commit()
    return {"confirmations": report.confirmations, "severity": report.severity}


@app.get("/api/reports/{report_id}/reasoning")
async def get_report_reasoning(report_id: int, db: Session = Depends(get_db)):
    report = db.query(Report).filter(Report.id == report_id).first()
    if not report:
        return JSONResponse(status_code=404, content={"error": "Report not found"})
    cutoff = datetime.now() - timedelta(days=7)
    nearby_count = db.query(Report).filter(
        Report.id != report.id,
        Report.category == report.category,
        Report.latitude.between(report.latitude - 0.002, report.latitude + 0.002),
        Report.longitude.between(report.longitude - 0.002, report.longitude + 0.002),
        Report.created_at >= cutoff,
    ).count()
    return generate_reasoning(report, nearby_count)


@app.get("/api/reports/similarity-clusters")
async def get_similarity_clusters(
    city: str = "stuttgart", threshold: int = 12, db: Session = Depends(get_db)
):
    if not (0 <= threshold <= 32):
        return JSONResponse(status_code=422, content={
            "error": {"code": "INVALID_THRESHOLD", "message": "Threshold must be between 0 and 32"}
        })
    city_key, _ = get_city(city)
    raw = find_similarity_clusters(city_key, threshold, db)
    # Enrich and sort by size descending
    reports_map = {}
    all_ids = [rid for c in raw for rid in c["report_ids"]]
    if all_ids:
        reports_map = {r.id: r for r in db.query(Report).filter(Report.id.in_(all_ids)).all()}
    clusters = []
    for c in sorted(raw, key=lambda x: len(x["report_ids"]), reverse=True):
        members = [reports_map[rid] for rid in c["report_ids"] if rid in reports_map]
        if len(members) < 2:
            continue
        cats = [m.category for m in members]
        neighs = [neighborhood_for_coords(m.latitude, m.longitude, city_key) for m in members]
        rids = [m.id for m in members]
        clusters.append({
            "cluster_id": len(clusters) + 1,
            "report_ids": rids,
            "size": len(rids),
            "avg_hamming_distance": c["avg_hamming_distance"],
            "common_category": Counter(cats).most_common(1)[0][0] if cats else None,
            "common_neighborhood": Counter(neighs).most_common(1)[0][0] if neighs else None,
        })
    return {"clusters": clusters, "total_clusters": len(clusters), "threshold": threshold, "city": city_key}


@app.get("/api/reports/{report_id}/duplicates")
async def get_report_duplicates(report_id: int, db: Session = Depends(get_db)):
    report = db.query(Report).filter(Report.id == report_id).first()
    if not report:
        return JSONResponse(status_code=404, content={"error": "Report not found"})
    try:
        dupes = find_duplicates(report_id, db)
    except Exception:
        return JSONResponse(status_code=422, content={"error": "Could not compute hash for this report"})
    return dupes


@app.get("/api/reports/{report_id}/cascade")
async def get_report_cascade(report_id: int, db: Session = Depends(get_db)):
    report = db.query(Report).filter(Report.id == report_id).first()
    if not report:
        return JSONResponse(status_code=404, content={"error": "Report not found"})
    city = report.city or "stuttgart"
    cutoff = datetime.now() - timedelta(days=7)
    nearby_count = db.query(Report).filter(
        Report.id != report.id, Report.category == report.category,
        Report.latitude.between(report.latitude - 0.002, report.latitude + 0.002),
        Report.longitude.between(report.longitude - 0.002, report.longitude + 0.002),
        Report.created_at >= cutoff,
    ).count()
    scale, shape = sla_params(report.category, report.severity)
    try:
        dupes = find_duplicates(report_id, db)[:3]
    except Exception:
        dupes = []
    return {
        "report": {"id": report.id, "category": report.category, "severity": report.severity,
                   "department": report.department, "status": report.status,
                   "created_at": report.created_at.isoformat()},
        "pipeline": get_pipeline_status(report),
        "reasoning": generate_reasoning(report, nearby_count),
        "priority": compute_priority(report, city),
        "sla": {"scale": scale, "shape": shape,
                "median_hours": round(sla_percentile(0.5, scale, shape), 1),
                "p75_hours": round(sla_percentile(0.75, scale, shape), 1),
                "p90_hours": round(sla_percentile(0.90, scale, shape), 1)},
        "duplicates": dupes,
    }


@app.patch("/api/reports/{report_id}/status")
async def update_report_status(report_id: int, request: Request, db: Session = Depends(get_db)):
    report = db.query(Report).filter(Report.id == report_id).first()
    if not report:
        return JSONResponse(status_code=404, content={"error": "Report not found"})
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=422, content={"error": {"code": "INVALID_JSON", "message": "Invalid JSON body"}})
    status = body.get("status") if isinstance(body, dict) else None
    if status not in VALID_STATUSES:
        return JSONResponse(status_code=422, content={"error": {"code": "INVALID_STATUS", "message": "Status must be one of: open, in_progress, resolved"}})
    report.status = status
    db.commit()
    db.refresh(report)
    return {
        "id": report.id, "status": report.status,
        "category": report.category, "severity": report.severity,
    }


CHAT_SYSTEM_PROMPT = """You are CityPulse AI, a smart assistant for {city}. You know about urban issues, infrastructure, and local news.

REPORT DATA:
{report_stats}

LOCAL NEWS:
{news_headlines}

Rules:
- Answer any question about {city} — urban issues, safety, transport, life, news, anything city-related
- For questions outside {city} scope (other cities, unrelated topics), give a brief honest answer if you can, then mention you specialize in {city}
- NEVER refuse to answer by just saying "I focus on urban issues". Always try to be helpful first.
- NEVER say "I don't have real-time data" or "I don't have information on that". Instead say something useful or suggest where to look.
- Do NOT confuse news headlines with citizen reports. News and reports are separate data sources.
- Use the report data and news above as your primary source. Cite specific numbers and locations.
- Keep answers to 1-3 sentences. Lead with the answer. No filler.
- If someone asks a vague question like "everything" or "tell me more", give a quick summary: health score, top issue category, busiest neighborhood, and trend.
- Never say "I don't have real-time data"
- Never ask "how can I help you" — just answer the question"""

CHAT_CITY = None  # Deprecated — city is now dynamic


def _build_report_stats(db: Session, city: Optional[str] = None) -> str:
    """Build a text summary of report data for the chat system prompt."""
    reports, stats = _build_dashboard_data(db, city=city)
    city_key = stats["city_key"]
    if stats["total_reports"] == 0:
        return "No reports have been submitted yet."
    lines = [f"Total reports: {stats['total_reports']}"]
    lines.append(f"Health score: {stats['health_score']:.1f}/100")
    lines.append(f"Trend: {stats['trend_text']}")
    if stats["categories"]:
        cats = ", ".join(f"{k}: {v}" for k, v in stats["categories"].items())
        lines.append(f"By category: {cats}")
    if stats["severities"]:
        sevs = ", ".join(f"{k}: {v}" for k, v in stats["severities"].items())
        lines.append(f"By severity: {sevs}")
    if stats["hotspots"]:
        spots = ", ".join(f"{h['name']} ({h['count']} reports)" for h in stats["hotspots"])
        lines.append(f"Top hotspots: {spots}")

    # Per-category status breakdown and resolution rates
    cat_status: dict[str, dict[str, int]] = {}
    for r in reports:
        cat_status.setdefault(r.category, {"open": 0, "in_progress": 0, "resolved": 0})
        cat_status[r.category][r.status] = cat_status[r.category].get(r.status, 0) + 1
    if cat_status:
        lines.append("\nCATEGORY STATUS & RESOLUTION RATES:")
        for cat, st in sorted(cat_status.items(), key=lambda x: sum(x[1].values()), reverse=True):
            total = sum(st.values())
            res_pct = round(st["resolved"] / total * 100) if total else 0
            lines.append(f"- {cat}: {st['open']} open, {st['in_progress']} in progress, {st['resolved']} resolved ({res_pct}% resolution rate)")

    # Risk scores by neighborhood (top 7)
    risk_scores = compute_risk_scores(reports, city_key)
    if risk_scores:
        lines.append("\nNEIGHBORHOOD RISK SCORES (highest risk first):")
        for rs in risk_scores[:7]:
            lines.append(f"- {rs['name']}: grade {rs['grade']}, risk {rs['risk_score']}/100")

    # Per-neighborhood breakdown (top 7 by report count)
    nh_data: dict[str, list] = {}
    for r in reports:
        nh = neighborhood_for_coords(r.latitude, r.longitude, city_key)
        nh_data.setdefault(nh, []).append(r)
    if nh_data:
        lines.append("\nNEIGHBORHOOD BREAKDOWN (top areas):")
        for nh, reps in sorted(nh_data.items(), key=lambda x: len(x[1]), reverse=True)[:7]:
            cats = Counter(r.category for r in reps)
            top_cats = ", ".join(f"{c}: {n}" for c, n in cats.most_common(3))
            sevs = Counter(r.severity for r in reps)
            sev_str = ", ".join(f"{s}: {n}" for s, n in sevs.most_common())
            unresolved = sum(1 for r in reps if r.status != "resolved")
            lines.append(f"- {nh} ({len(reps)} reports): categories [{top_cats}], severity [{sev_str}], {unresolved} unresolved")

    # Recent individual reports for specific-question answering
    cutoff = datetime.now() - timedelta(days=7)
    recent = sorted(
        [r for r in reports if r.created_at >= cutoff],
        key=lambda r: r.created_at, reverse=True,
    )[:20]
    if recent:
        lines.append("\nRECENT INDIVIDUAL REPORTS (last 7 days):")
        for r in recent:
            ts = r.created_at.strftime("%Y-%m-%d %H:%M")
            loc = neighborhood_for_coords(r.latitude, r.longitude, city_key)
            desc = (r.description[:100] + "...") if len(r.description) > 100 else r.description
            lines.append(f"- [{ts}] {r.category} ({r.severity}) near {loc} — {desc}")
    return "\n".join(lines)


@app.post("/api/chat")
async def chat(request: Request, db: Session = Depends(get_db)):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=422, content={"error": {"code": "INVALID_JSON", "message": "Invalid JSON body"}})

    message = body.get("message", "").strip() if isinstance(body, dict) else ""
    if not message:
        return JSONResponse(status_code=422, content={"error": {"code": "EMPTY_MESSAGE", "message": "Message is required"}})

    city_key = body.get("city") if isinstance(body, dict) else None
    city_key, city_cfg = get_city(city_key)
    city_name = city_cfg["name"]

    try:
        report_stats = _build_report_stats(db, city=city_key)
        news = await fetch_news(city_key)
        news_text = "\n".join(f"- {n['title']}" for n in news) if news else "No recent news available."

        system_prompt = CHAT_SYSTEM_PROMPT.format(
            city=city_name, report_stats=report_stats, news_headlines=news_text,
        )

        api_key = os.environ.get("GROQ_API_KEY", "")
        if not api_key:
            return {"response": "I'm having trouble right now. Please try again."}

        async with httpx.AsyncClient() as client:
            r = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                json={
                    "model": "llama-3.1-8b-instant",
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": message},
                    ],
                    "max_tokens": 512,
                },
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                timeout=10,
            )
        r.raise_for_status()
        answer = r.json()["choices"][0]["message"]["content"]
        return {"response": answer}
    except Exception:
        return {"response": "I'm having trouble right now. Please try again."}


BRIEFING_PROMPT = """You are a municipal analyst writing a formal city council briefing for {city}.

DATA:
{data}

Write exactly 3 paragraphs:
1. Executive summary — overall city health, total reports, trend
2. Key findings — cite specific numbers, categories, severity counts, and neighborhood names
3. Recommended priorities for city departments — actionable, based on the data

Style: formal city council memo. Cite specific numbers. No greetings or sign-offs."""


def _build_briefing_data(db: Session, city: Optional[str] = None) -> tuple:
    """Build briefing prompt data and stats dict. Returns (prompt_data_str, stats, reports)."""
    reports, stats = _build_dashboard_data(db, city=city)
    city_key = stats["city_key"]
    lines = [
        f"Total reports: {stats['total_reports']}",
        f"Health score: {stats['health_score']:.1f}/100",
        f"Trend: {stats['trend_text']}",
    ]
    if stats["categories"]:
        lines.append("Categories: " + ", ".join(f"{k}: {v}" for k, v in stats["categories"].items()))
    if stats["severities"]:
        lines.append("Severity: " + ", ".join(f"{k}: {v}" for k, v in stats["severities"].items()))
    if stats["hotspots"]:
        lines.append("Top hotspots: " + ", ".join(f"{h['name']} ({h['count']} reports)" for h in stats["hotspots"]))
    cutoff = datetime.now() - timedelta(days=7)
    critical = [r for r in reports if r.created_at >= cutoff and r.severity in ("critical", "high")]
    critical.sort(key=lambda r: r.created_at, reverse=True)
    for r in critical[:5]:
        loc = neighborhood_for_coords(r.latitude, r.longitude, city_key)
        desc = (r.description[:80] + "...") if len(r.description) > 80 else r.description
        lines.append(f"- {r.category} ({r.severity}) near {loc}: {desc}")
    return "\n".join(lines), stats, reports


def _fallback_briefing(stats: dict) -> str:
    """Generate a data-driven fallback briefing without AI."""
    total = stats["total_reports"]
    score = stats["health_score"]
    trend = stats["trend_text"]
    city_name = stats["city_cfg"]["name"]
    top_cat = max(stats["categories"], key=stats["categories"].get) if stats["categories"] else "N/A"
    top_cat_n = stats["categories"].get(top_cat, 0)
    hotspot = stats["hotspots"][0]["name"] if stats["hotspots"] else "N/A"
    sev = stats["severities"]
    crit = sev.get("critical", 0) + sev.get("high", 0)
    return (
        f"As of {datetime.now().strftime('%B %d, %Y')}, {city_name}'s CityPulse system has recorded "
        f"{total} citizen reports with a city health score of {score:.1f}/100. {trend}.\n\n"
        f"The most reported category is {top_cat} with {top_cat_n} reports. "
        f"{crit} reports are classified as high or critical severity. "
        f"The highest-activity area is {hotspot}.\n\n"
        f"City departments should prioritize {top_cat} issues and focus resources on the {hotspot} area."
    )


async def _generate_briefing(db: Session, city: Optional[str] = None) -> dict:
    """Generate briefing dict with 'briefing' and 'generated_at' keys."""
    data_str, stats, _ = _build_briefing_data(db, city=city)
    city_name = stats["city_cfg"]["name"]
    generated_at = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")

    if stats["total_reports"] == 0:
        return {"briefing": "No reports have been submitted yet. The briefing will be available once citizen reports are recorded.", "generated_at": generated_at}

    try:
        api_key = os.environ.get("GROQ_API_KEY", "")
        if not api_key:
            return {"briefing": _fallback_briefing(stats), "generated_at": generated_at}

        async with httpx.AsyncClient() as client:
            r = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                json={
                    "model": "llama-3.1-8b-instant",
                    "messages": [
                        {"role": "system", "content": BRIEFING_PROMPT.format(city=city_name, data=data_str)},
                        {"role": "user", "content": "Generate the city council briefing."},
                    ],
                    "max_tokens": 1024,
                },
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                timeout=15,
            )
        r.raise_for_status()
        text = r.json()["choices"][0]["message"]["content"]
        return {"briefing": text, "generated_at": generated_at}
    except Exception:
        return {"briefing": _fallback_briefing(stats), "generated_at": generated_at}


@app.get("/api/briefing")
async def api_briefing(db: Session = Depends(get_db), city: Optional[str] = None):
    return await _generate_briefing(db, city=city)


@app.get("/api/budget/optimize")
def budget_optimize(city: Optional[str] = None, budget: float = 100000.0, db: Session = Depends(get_db)):
    import math
    if budget <= 0 or not math.isfinite(budget):
        return JSONResponse({"error": "Budget must be a positive finite number"}, status_code=400)
    city_key, _ = get_city(city)
    return optimize_budget(city_key, budget, db)


@app.get("/api/dispatch/optimize")
def dispatch_optimize(city: Optional[str] = None, crews: int = 3, db: Session = Depends(get_db)):
    if crews <= 0 or crews > 50:
        return JSONResponse({"error": "crews must be between 1 and 50"}, status_code=400)
    city_key, _ = get_city(city)
    return optimize_dispatch(city_key, crews, db)


@app.get("/api/predict/diffusion")
def predict_diffusion(city: Optional[str] = None, horizon: int = 7, db: Session = Depends(get_db)):
    if horizon not in (7, 14, 30):
        return JSONResponse({"error": "horizon must be 7, 14, or 30"}, status_code=400)
    city_key, _ = get_city(city)
    return compute_diffusion(city_key, horizon, db)


@app.get("/api/causality")
def causality(city: Optional[str] = None, db: Session = Depends(get_db)):
    city_key, _ = get_city(city)
    return compute_causality(city_key, db)


@app.get("/api/neighborhoods/compare")
def neighborhoods_compare(a: str, b: str, city: Optional[str] = None, db: Session = Depends(get_db)):
    city_key, cfg = get_city(city)
    bbox_map = {name: (lat_min, lat_max, lng_min, lng_max)
                for lat_min, lat_max, lng_min, lng_max, name in cfg["neighborhoods"]}
    invalid = [n for n in (a, b) if n not in bbox_map]
    if invalid:
        return JSONResponse({"error": f"Unknown neighborhood(s): {', '.join(invalid)}"}, status_code=422)
    reports = db.query(Report).filter(Report.city == city_key).all()
    results = []
    for name in (a, b):
        lat_min, lat_max, lng_min, lng_max = bbox_map[name]
        matched = [r for r in reports if lat_min <= r.latitude <= lat_max and lng_min <= r.longitude <= lng_max]
        count = len(matched)
        cats = Counter(r.category for r in matched)
        avg_sev = (sum(SEVERITY_WEIGHTS.get(r.severity, 1) for r in matched) / count) if count else 0
        res_rate = (sum(1 for r in matched if r.status == "resolved") / count) if count else 0
        state = anomaly_get_state(city_key, name)
        results.append({
            "name": name, "report_count": count,
            "health_score": round(compute_health_score(matched), 1),
            "top_category": cats.most_common(1)[0][0] if cats else None,
            "avg_severity": round(avg_sev, 2), "resolution_rate": round(res_rate, 2),
            "anomaly_active": state is not None and state["last_alert"] > 0,
        })
    return {"city": city_key, "neighborhoods": results}


@app.get("/api/reports/age-distribution")
def report_age_distribution(city: Optional[str] = None, db: Session = Depends(get_db)):
    city_key, _ = get_city(city)
    now = datetime.utcnow()
    open_reports = db.query(Report).filter(Report.city == city_key, Report.status != "resolved").all()
    ages = sorted([(now - r.created_at).total_seconds() / 3600 for r in open_reports])
    total = len(ages)
    bucket_defs = [("0-24h",0,24),("1-3d",24,72),("3-7d",72,168),("7-14d",168,336),("14-30d",336,720),("30d+",720,None)]
    buckets = []
    for label, lo, hi in bucket_defs:
        count = sum(1 for a in ages if a >= lo and (hi is None or a < hi))
        buckets.append({"label": label, "min_hours": lo, "max_hours": hi,
                        "count": count, "percentage": round(count * 100 / total, 1) if total else 0})
    if total:
        mid = total // 2
        median = (ages[mid] if total % 2 else (ages[mid - 1] + ages[mid]) / 2)
    else:
        median = 0
    return {"city": city_key, "total_open": total, "buckets": buckets,
            "median_age_hours": round(median, 1), "oldest_report_hours": round(ages[-1], 1) if ages else 0}


@app.get("/api/departments/efficiency")
def department_efficiency(city: Optional[str] = None, db: Session = Depends(get_db)):
    city_key, _ = get_city(city)
    now = datetime.utcnow()
    reports = db.query(Report).filter(Report.city == city_key).all()
    total_all = len(reports)
    if not total_all:
        return {"city": city_key, "departments": []}
    depts: dict = {}
    for r in reports:
        d = depts.setdefault(r.department, {"total": 0, "resolved": 0, "open_ages": []})
        d["total"] += 1
        if r.status == "resolved":
            d["resolved"] += 1
        else:
            d["open_ages"].append((now - r.created_at).total_seconds() / 3600)
    results = []
    for name, d in depts.items():
        res_rate = d["resolved"] / d["total"]
        avg_age = sum(d["open_ages"]) / len(d["open_ages"]) if d["open_ages"] else 0.0
        results.append({"name": name, "total_reports": d["total"], "resolved_count": d["resolved"],
                        "resolution_rate": round(res_rate, 4), "avg_age_hours": round(avg_age, 1),
                        "workload_share": round(d["total"] / total_all, 4)})
    max_age = max(r["avg_age_hours"] for r in results)
    for r in results:
        norm_age = (r["avg_age_hours"] / max_age) if max_age > 0 else 0.0
        r["efficiency_score"] = round(r["resolution_rate"] * 0.6 + (1 - norm_age) * 0.4, 4)
    results.sort(key=lambda x: x["efficiency_score"], reverse=True)
    for i, r in enumerate(results, 1):
        r["rank"] = i
    return {"city": city_key, "departments": results}


@app.get("/briefing")
async def briefing_page(request: Request, db: Session = Depends(get_db), city: Optional[str] = None):
    city_key, _ = get_city(city)
    data = await _generate_briefing(db, city=city)
    data["city"] = city_key
    data["cities"] = CITIES
    return templates.TemplateResponse(request, "briefing.html", data)
