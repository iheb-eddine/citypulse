"""Seed script: populates CityPulse DB with 50 reports using Mapillary street photos + Pexels fallback."""

import os
import random
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4

import httpx
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from app.database import SessionLocal, create_tables
from app.models import Report
from app.classifier import classify_image

random.seed(42)

UPLOAD_DIR = Path(__file__).resolve().parent.parent / "app" / "static" / "uploads"

MAPILLARY_TOKEN = os.environ.get("MAPILLARY_TOKEN", "")
MAPILLARY_URL = "https://graph.mapillary.com/images"

PEXELS_KEY = os.environ.get("PEXELS_API_KEY", "")
PEXELS_URL = "https://api.pexels.com/v1/search"

CATEGORY_QUERIES = {
    "pothole": "pothole road damage",
    "streetlight": "broken street light night",
    "graffiti": "graffiti urban wall",
    "flooding": "street flooding rain",
    "dumping": "illegal dumping trash street",
    "sign": "damaged road sign",
    "other": "broken urban infrastructure",
}

DEPT_MAP = {
    "pothole": "roads", "streetlight": "electrical", "graffiti": "sanitation",
    "flooding": "water", "dumping": "sanitation", "sign": "roads", "other": "general",
}

DESCRIPTIONS = {
    "pothole": [
        "Deep pothole on main road near intersection", "Crumbling asphalt with exposed gravel",
        "Wide pothole spanning half the lane", "Pothole filled with standing water after rain",
        "Series of small potholes along curb", "Large pothole near pedestrian crossing",
        "Pothole with sharp edges damaging tires", "Sinking road surface forming pothole",
    ],
    "streetlight": [
        "Streetlight flickering intermittently at night", "Broken streetlight leaving dark stretch",
        "Leaning light pole after vehicle impact", "Streetlight stays on during daytime",
        "Shattered lamp cover with exposed bulb",
    ],
    "graffiti": [
        "Large graffiti tag on retaining wall", "Spray paint on bus shelter glass",
        "Offensive graffiti on school fence", "Graffiti covering traffic sign",
    ],
    "flooding": [
        "Blocked storm drain causing street flooding", "Water pooling at underpass after rain",
        "Overflowing drainage ditch near sidewalk",
    ],
    "dumping": [
        "Illegal furniture dumped near recycling bins", "Construction debris left on sidewalk",
        "Bags of household waste dumped in park",
    ],
    "sign": [
        "Bent stop sign barely visible to drivers", "Missing street name sign at intersection",
        "Faded speed limit sign unreadable",
    ],
    "other": ["Broken bench in public park", "Damaged guardrail on bridge"],
}

SEVERITIES = ["low", "medium", "high", "critical"]

HAUPTBAHNHOF = [(48.7842 + random.uniform(-0.001, 0.001),
                  9.1816 + random.uniform(-0.001, 0.001)) for _ in range(8)]
BAD_CANNSTATT = [(48.8044 + random.uniform(-0.001, 0.001),
                   9.2140 + random.uniform(-0.001, 0.001)) for _ in range(5)]

STUTTGART_LOCATIONS = [
    (48.7710, 9.1700), (48.7620, 9.1690), (48.7900, 9.1950),
    (48.7680, 9.2100), (48.7550, 9.1600), (48.7450, 9.1750),
    (48.7780, 9.1550), (48.8100, 9.2300), (48.7350, 9.1500),
    (48.7950, 9.1400), (48.7600, 9.1900), (48.7500, 9.2050),
    (48.7850, 9.1600), (48.7700, 9.2200), (48.7400, 9.1850),
]


def fetch_mapillary_image(lat: float, lng: float, client: httpx.Client) -> bytes | None:
    """Fetch a street-level photo near the given coordinates from Mapillary. Tries progressively wider areas."""
    for delta in [0.003, 0.006, 0.01, 0.02, 0.04]:
        try:
            r = client.get(MAPILLARY_URL, params={
                "access_token": MAPILLARY_TOKEN,
                "fields": "id,thumb_1024_url",
                "bbox": f"{lng-delta},{lat-delta},{lng+delta},{lat+delta}",
                "limit": 1,
            }, timeout=15)
            r.raise_for_status()
            data = r.json().get("data", [])
            if data and "thumb_1024_url" in data[0]:
                img_r = client.get(data[0]["thumb_1024_url"], timeout=15, follow_redirects=True)
                img_r.raise_for_status()
                return img_r.content
        except Exception:
            continue
    return None


def fetch_pexels_fallback(category: str, client: httpx.Client) -> bytes | None:
    """Fetch a category-relevant photo from Pexels as fallback."""
    query = CATEGORY_QUERIES.get(category, "urban infrastructure")
    try:
        r = client.get(PEXELS_URL, params={"query": query, "per_page": 5, "size": "small"},
                       headers={"Authorization": PEXELS_KEY}, timeout=15)
        r.raise_for_status()
        photos = r.json().get("photos", [])
        if not photos:
            return None
        url = random.choice(photos)["src"]["medium"]
        img_r = client.get(url, timeout=15, follow_redirects=True)
        img_r.raise_for_status()
        return img_r.content
    except Exception:
        return None


def save_image(data: bytes) -> str:
    """Save image bytes, return filename."""
    # Detect format from magic bytes
    ext = ".jpg"
    if data[:4] == b"\x89PNG":
        ext = ".png"
    elif data[:4] == b"RIFF":
        ext = ".webp"
    fname = f"seed_{uuid4().hex[:12]}{ext}"
    (UPLOAD_DIR / fname).write_bytes(data)
    return fname


def make_placeholder() -> str:
    """Last resort: tiny gray placeholder."""
    from PIL import Image
    img = Image.new("RGB", (100, 100), (180, 180, 180))
    fname = f"seed_{uuid4().hex[:12]}.png"
    img.save(UPLOAD_DIR / fname)
    return fname


def build_reports() -> list[dict]:
    reports = []
    for i, (lat, lng) in enumerate(HAUPTBAHNHOF):
        reports.append({"category": "pothole", "severity": random.choice(["high", "critical"]),
                        "latitude": lat, "longitude": lng,
                        "description": DESCRIPTIONS["pothole"][i], "days_ago": random.uniform(0, 13)})
    for i, (lat, lng) in enumerate(BAD_CANNSTATT):
        reports.append({"category": "streetlight", "severity": random.choice(["medium", "high"]),
                        "latitude": lat, "longitude": lng,
                        "description": DESCRIPTIONS["streetlight"][i], "days_ago": random.uniform(0, 13)})
    scattered_cats = ["graffiti", "flooding", "dumping", "sign", "other", "pothole", "streetlight"]
    guaranteed = [(random.choice(scattered_cats), sev) for sev in SEVERITIES]
    extra = [(random.choice(scattered_cats), random.choice(SEVERITIES)) for _ in range(33)]
    scattered = guaranteed + extra
    random.shuffle(scattered)
    for i, (cat, sev) in enumerate(scattered):
        loc = STUTTGART_LOCATIONS[i % len(STUTTGART_LOCATIONS)]
        reports.append({"category": cat, "severity": sev,
                        "latitude": loc[0] + random.uniform(-0.003, 0.003),
                        "longitude": loc[1] + random.uniform(-0.003, 0.003),
                        "description": random.choice(DESCRIPTIONS[cat]),
                        "days_ago": random.uniform(0, 13)})
    return reports


def main():
    create_tables()
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    for ext in ("*.png", "*.jpg", "*.webp"):
        for f in UPLOAD_DIR.glob(ext):
            f.unlink()

    db = SessionLocal()
    client = httpx.Client(timeout=15)
    try:
        db.query(Report).delete()
        db.commit()

        now = datetime.now()
        report_defs = build_reports()
        mapillary_ok = 0
        skipped = 0

        for i, rd in enumerate(report_defs):
            # Mapillary only — skip reports without real photos
            img_data = None
            if MAPILLARY_TOKEN:
                img_data = fetch_mapillary_image(rd["latitude"], rd["longitude"], client)

            if not img_data:
                skipped += 1
                continue

            fname = save_image(img_data)

            # Classify image with AI
            classification = classify_image(img_data)
            print(f"\r  [{i+1}/50] → {classification['category']} ({classification['severity']})", end="", flush=True)
            time.sleep(2)  # Rate limit: free tier ~30 req/min

            report = Report(
                photo_path=f"/static/uploads/{fname}",
                latitude=rd["latitude"], longitude=rd["longitude"],
                category=classification["category"],
                severity=classification["severity"],
                department=classification["department"],
                description=classification["description"],
                created_at=now - timedelta(days=rd["days_ago"]),
            )
            db.add(report)
            print(f"\r  [{i+1}/50]", end="", flush=True)

        db.commit()
        print()

        count = db.query(Report).count()
        cats = {}
        for r in db.query(Report).all():
            cats[r.category] = cats.get(r.category, 0) + 1

        print(f"Seeded {count} reports.")
        print(f"  Mapillary photos: {count}")
        print(f"  Skipped (no coverage): {skipped}")
        print(f"Categories: {cats}")
    finally:
        client.close()
        db.close()


if __name__ == "__main__":
    main()
