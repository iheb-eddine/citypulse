"""CityPulse FastAPI application — routes, templates, static files."""

from collections import Counter
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from uuid import uuid4

import folium
import numpy as np
from fastapi import Depends, FastAPI, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

import httpx
import os

from dotenv import load_dotenv

from app.database import create_tables, get_db
from app.gemini import classify_image, FALLBACK
from app.models import Report
from app.news import fetch_news

load_dotenv()

SEVERITY_COLORS = {"low": "green", "medium": "orange", "high": "orange", "critical": "red"}
SEVERITY_WEIGHTS = {"low": 1, "medium": 2, "high": 3, "critical": 5}


def compute_health_score(reports: list) -> float:
    if not reports:
        return 100
    weighted_sum = sum(SEVERITY_WEIGHTS.get(r.severity, 1) for r in reports)
    return max(0, 100 - (weighted_sum / len(reports)) * 20)


def compute_trend(reports: list, now: Optional[datetime] = None) -> int:
    now = now or datetime.now()
    week_ago = now - timedelta(days=7)
    two_weeks_ago = now - timedelta(days=14)
    current = sum(1 for r in reports if r.created_at >= week_ago)
    previous = sum(1 for r in reports if two_weeks_ago <= r.created_at < week_ago)
    return current - previous


def compute_category_breakdown(reports: list) -> dict:
    return dict(Counter(r.category for r in reports))


def compute_severity_breakdown(reports: list) -> dict:
    return dict(Counter(r.severity for r in reports))


# Stuttgart neighborhood bounding boxes: (lat_min, lat_max, lng_min, lng_max) -> name
NEIGHBORHOODS = [
    (48.781, 48.788, 9.177, 9.186, "Hauptbahnhof"),
    (48.800, 48.809, 9.209, 9.219, "Bad Cannstatt"),
    (48.767, 48.775, 9.164, 9.176, "Stuttgart-West"),
    (48.757, 48.767, 9.164, 9.176, "Stuttgart-Süd"),
    (48.786, 48.795, 9.188, 9.202, "Stuttgart-Nord"),
    (48.764, 48.773, 9.204, 9.216, "Stuttgart-Ost"),
    (48.750, 48.759, 9.153, 9.167, "Vaihingen"),
    (48.741, 48.750, 9.170, 9.182, "Möhringen"),
    (48.774, 48.782, 9.150, 9.162, "Botnang"),
    (48.806, 48.815, 9.225, 9.236, "Münster"),
    (48.730, 48.740, 9.145, 9.156, "Büsnau"),
    (48.791, 48.800, 9.135, 9.148, "Feuerbach"),
    (48.756, 48.764, 9.184, 9.196, "Degerloch"),
    (48.746, 48.755, 9.200, 9.212, "Sillenbuch"),
    (48.781, 48.790, 9.155, 9.167, "Zuffenhausen"),
    (48.766, 48.775, 9.215, 9.226, "Wangen"),
    (48.736, 48.745, 9.180, 9.192, "Plieningen"),
]


def neighborhood_for_coords(lat: float, lng: float) -> str:
    for lat_min, lat_max, lng_min, lng_max, name in NEIGHBORHOODS:
        if lat_min <= lat <= lat_max and lng_min <= lng <= lng_max:
            return name
    # Check if within greater Stuttgart area
    if 48.70 <= lat <= 48.85 and 9.10 <= lng <= 9.30:
        return "Stuttgart"
    return "Unknown area"


def compute_hotspots(reports: list) -> list:
    clusters = Counter(r.cluster_id for r in reports if r.cluster_id is not None)
    hotspots = []
    for cid, cnt in clusters.most_common(3):
        cluster_reports = [r for r in reports if r.cluster_id == cid]
        avg_lat = sum(r.latitude for r in cluster_reports) / len(cluster_reports)
        avg_lng = sum(r.longitude for r in cluster_reports) / len(cluster_reports)
        name = neighborhood_for_coords(avg_lat, avg_lng)
        hotspots.append({"cluster_id": cid, "count": cnt, "name": name})
    return hotspots


def run_clustering(reports: list[Report], db: Session) -> None:
    """Run DBSCAN on report coordinates and update cluster_id in DB."""
    if not reports:
        return
    from sklearn.cluster import DBSCAN
    coords = np.array([[r.latitude, r.longitude] for r in reports])
    labels = DBSCAN(eps=0.003, min_samples=3, metric="euclidean").fit_predict(coords)
    for report, label in zip(reports, labels):
        report.cluster_id = None if label == -1 else int(label)
    db.commit()

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "static" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

MAX_FILE_SIZE = 10_485_760

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


def _error(code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=422, content={"error": {"code": code, "message": message}})


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_tables()
    yield


app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


@app.get("/submit")
async def submit_page(request: Request):
    return templates.TemplateResponse(request, "submit.html")


VALID_CATEGORIES = {"pothole", "streetlight", "graffiti", "flooding", "dumping", "sign", "other", "unclassified"}
VALID_SEVERITIES = {"low", "medium", "high", "critical"}


def _build_dashboard_data(db: Session, category: Optional[str] = None, severity: Optional[str] = None):
    """Shared logic for dashboard HTML and API."""
    all_reports = db.query(Report).all()
    run_clustering(all_reports, db)

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
    hotspots = compute_hotspots(reports)
    total = len(reports)

    if trend > 0:
        trend_text = f"↑ {trend} more reports this week"
    elif trend < 0:
        trend_text = f"↓ {abs(trend)} fewer reports this week"
    else:
        trend_text = "→ Same as last week"

    return reports, {
        "health_score": health_score, "total_reports": total,
        "categories": categories, "severities": severities,
        "hotspots": hotspots, "trend_text": trend_text, "trend": trend,
    }


@app.get("/")
@app.get("/dashboard")
async def dashboard(
    request: Request, db: Session = Depends(get_db),
    category: Optional[str] = None, severity: Optional[str] = None,
):
    reports, stats = _build_dashboard_data(db, category, severity)
    m = folium.Map(location=[48.7758, 9.1829], zoom_start=13)
    SEV_BADGE = {"low": "#43a047", "medium": "#fb8c00", "high": "#f4511e", "critical": "#c62828"}
    bounds = []
    for r in reports:
        sev_color = SEV_BADGE.get(r.severity, "#1a73e8")
        popup_html = (
            f'<div style="font-family:-apple-system,BlinkMacSystemFont,sans-serif;min-width:160px">'
            f'<img src="{r.photo_path}" width="160" style="border-radius:6px;display:block;margin-bottom:6px">'
            f'<div style="font-weight:700;font-size:13px;margin-bottom:4px;text-transform:capitalize">{r.category}</div>'
            f'<span style="display:inline-block;background:{sev_color};color:#fff;padding:1px 8px;border-radius:10px;font-size:11px;font-weight:600;text-transform:uppercase">{r.severity}</span>'
            f'<div style="color:#5f6b7a;font-size:11px;margin-top:6px">{r.department}<br>{r.created_at}</div>'
            f'</div>'
        )
        folium.Marker(
            location=[r.latitude, r.longitude],
            popup=folium.Popup(popup_html, max_width=220),
            icon=folium.Icon(color=SEVERITY_COLORS.get(r.severity, "blue")),
        ).add_to(m)
        bounds.append([r.latitude, r.longitude])
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
        },
    )


@app.get("/api/dashboard")
async def api_dashboard(
    db: Session = Depends(get_db),
    category: Optional[str] = None, severity: Optional[str] = None,
):
    reports, stats = _build_dashboard_data(db, category, severity)
    return {
        **stats,
        "reports": [
            {
                "id": r.id, "photo_path": r.photo_path,
                "latitude": r.latitude, "longitude": r.longitude,
                "category": r.category, "severity": r.severity,
                "department": r.department, "description": r.description,
                "cluster_id": r.cluster_id, "created_at": str(r.created_at),
            }
            for r in reports
        ],
    }


@app.get("/api/reports")
async def get_reports(db: Session = Depends(get_db)):
    reports = db.query(Report).order_by(Report.created_at.desc()).all()
    return [
        {
            "id": r.id, "photo_path": r.photo_path,
            "latitude": r.latitude, "longitude": r.longitude,
            "category": r.category, "severity": r.severity,
            "department": r.department, "description": r.description,
            "cluster_id": r.cluster_id, "created_at": str(r.created_at),
        }
        for r in reports
    ]


@app.post("/api/reports")
async def create_report(
    photo: Optional[UploadFile] = File(None),
    latitude: Optional[str] = Form(None),
    longitude: Optional[str] = Form(None),
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

    # 9. Classify image via Gemini (falls back automatically on any failure)
    result = classify_image(content)

    # 10. Create report
    report = Report(
        photo_path=f"/static/uploads/{filename}",
        latitude=lat,
        longitude=lng,
        **result,
    )
    db.add(report)
    db.commit()
    db.refresh(report)

    # 11. Return 201
    return JSONResponse(
        status_code=201,
        content={
            "id": report.id,
            "photo_path": report.photo_path,
            "latitude": report.latitude,
            "longitude": report.longitude,
            "category": report.category,
            "severity": report.severity,
            "department": report.department,
            "description": report.description,
            "created_at": str(report.created_at),
        },
    )


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

CHAT_CITY = "Stuttgart"


def _build_report_stats(db: Session) -> str:
    """Build a text summary of report data for the chat system prompt."""
    reports, stats = _build_dashboard_data(db)
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
    # Append individual recent reports for specific-question answering
    cutoff = datetime.now() - timedelta(days=7)
    recent = sorted(
        [r for r in reports if r.created_at >= cutoff],
        key=lambda r: r.created_at, reverse=True,
    )[:20]
    if recent:
        lines.append("\nRECENT INDIVIDUAL REPORTS (last 7 days):")
        for r in recent:
            ts = r.created_at.strftime("%Y-%m-%d %H:%M")
            loc = neighborhood_for_coords(r.latitude, r.longitude)
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

    try:
        report_stats = _build_report_stats(db)
        news = fetch_news()
        news_text = "\n".join(f"- {n['title']}" for n in news) if news else "No recent news available."

        system_prompt = CHAT_SYSTEM_PROMPT.format(
            city=CHAT_CITY, report_stats=report_stats, news_headlines=news_text,
        )

        api_key = os.environ.get("GROQ_API_KEY", "")
        if not api_key:
            return {"response": "I'm having trouble right now. Please try again."}

        r = httpx.post(
            "https://api.groq.com/openai/v1/chat/completions",
            json={
                "model": "llama-3.1-8b-instant",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": message},
                ],
                "max_tokens": 200,
            },
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            timeout=10,
        )
        r.raise_for_status()
        answer = r.json()["choices"][0]["message"]["content"]
        return {"response": answer}
    except Exception:
        return {"response": "I'm having trouble right now. Please try again."}
