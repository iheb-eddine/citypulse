# 🏙️ CityPulse — AI-Powered Urban Issue Triage

> **Turn every citizen's phone into a smart city sensor.**

🌐 **Live at [citypulse.help](https://citypulse.help)** &nbsp;|&nbsp; 📦 [GitHub](https://github.com/iheb-eddine/citypulse)

[![Built for AlgoFest 2026](https://img.shields.io/badge/AlgoFest_2026-Smart_Cities_%26_IoT-1a73e8)](#)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)](#)
[![Tests](https://img.shields.io/badge/tests-47_passing-brightgreen)](#running-tests)

Citizens snap a photo of an urban issue — pothole, broken streetlight, illegal dumping — and CityPulse does the rest. AI classifies the problem in seconds, routes it to the right city department, and clusters hotspots on a live dashboard so resources go where they're needed most. City officials get auto-generated council briefings, and an AI chat assistant answers questions about urban trends using real report data and local news.

---

## ✨ Features

| Feature | Description |
|---|---|
| 📸 **Photo Upload & AI Classification** | Upload a photo → Groq Llama 4 Scout vision model classifies category, severity, and department instantly |
| 🗺️ **Interactive Map Dashboard** | Folium/Leaflet map with color-coded markers, popups with status controls, and layer toggle |
| 🔥 **Heatmap Density Overlay** | Heatmap overlay shows report density across the city |
| 📊 **DBSCAN Spatial Clustering** | Groups nearby reports into actionable hotspots (eps=0.003, min_samples=3) |
| 💯 **City Health Score** | Severity-weighted metric (0–100) — a single KPI for urban wellbeing |
| ♿ **Accessibility Impact Score** | Weighted score factoring category impact on mobility and accessibility |
| 💬 **AI Chat Assistant** | Ask questions about city reports, trends, or local news — powered by Groq with live report context |
| 📋 **AI City Council Briefing** | Auto-generated formal briefing with executive summary, findings, and recommendations |
| 📡 **Real-Time SSE Live Updates** | Server-Sent Events push new reports to all connected dashboards with toast notifications |
| 👍 **Citizen Upvote/Verify** | Confirm reports — 3 confirmations auto-escalate severity |
| 🔄 **Resolution Workflow** | Track reports through open → in_progress → resolved |
| 🌍 **GeoJSON Open Data API** | Standard GeoJSON endpoint for integration with external GIS tools |
| 🔒 **EXIF Stripping & Privacy Badge** | All photo metadata is automatically stripped before storage |
| 🎙️ **Voice Report Submission** | Describe issues by voice using Web Speech API (browser-native) |
| 🏙️ **Multi-City Support** | City selector with per-city neighborhoods, news feeds, and map bounds |
| 🌓 **Dark Mode** | System-aware + manual toggle, persisted in localStorage |
| 📱 **PWA Support** | Service worker + manifest for installable mobile experience |
| 📰 **Local News Integration** | RSS feeds filtered by city keywords, auto-translated to English via Groq |

---

## 🛠️ Tech Stack

| Technology | Role |
|---|---|
| **FastAPI** | Web framework and REST API |
| **SQLite + SQLAlchemy** | Database and ORM |
| **Groq API** | AI — Llama 4 Scout (vision classification), Llama 3.1 8B (chat, briefing, news translation) |
| **scikit-learn (DBSCAN)** | Geospatial clustering of reports |
| **Folium / Leaflet.js** | Interactive map with heatmap density overlay |
| **Pillow** | EXIF metadata stripping for privacy |
| **httpx** | HTTP client for Groq API, RSS feeds, seed data fetching |
| **Jinja2** | Server-side HTML templates |
| **NumPy** | Coordinate array processing for clustering |
| **python-dotenv** | Environment variable management |
| **Vanilla HTML/CSS/JS** | Mobile-responsive frontend — no framework needed |

---

## 🏗️ Architecture

```
┌─────────────┐                              ┌──────────────────┐
│   Mobile     │  POST /api/reports           │    FastAPI        │
│   Browser    │ ──── photo + GPS ──────────▶ │    Server         │
│              │                              │                  │
│              │  GET /api/stream (SSE)       │  ┌────────────┐  │
│              │ ◀──── live updates ───────── │  │ SSE Engine │  │
└─────────────┘                              │  └────────────┘  │
                                             └───────┬──────────┘
                                                     │
                              ┌───────────────┬──────┴──────┬──────────────┐
                              ▼               ▼             ▼              ▼
                       ┌────────────┐  ┌───────────┐ ┌──────────┐  ┌───────────┐
                       │ Groq API   │  │  SQLite   │ │  DBSCAN  │  │  RSS/News │
                       │ Llama 4    │  │  Database │ │ Clustering│  │  Fetcher  │
                       │ Scout      │  └─────┬─────┘ └──────────┘  └───────────┘
                       └─────┬──────┘        │
                             │               │
                    category, severity,      │
                    department, description  │
                             │               │
                             └───────┬───────┘
                                     ▼
┌─────────────┐  GET /dashboard    ┌──────────────────┐
│   Browser    │ ◀──── map + ───── │  Dashboard Route  │
│              │    stats + chat   │  + Folium Map Gen │
└─────────────┘                    │  + Health Score   │
                                   │  + Heatmap        │
                                   └──────────────────┘
```

---

## 📁 Project Structure

```
citypulse/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI routes, clustering, health score, chat, briefing, SSE
│   ├── database.py          # SQLAlchemy engine and session
│   ├── models.py            # Report model with constraints
│   ├── classifier.py            # AI classification client (Groq Llama 4 Scout) + fallback logic
│   ├── news.py              # RSS news fetcher with city filtering + Groq translation
│   ├── templates/
│   │   ├── submit.html      # Mobile-first report submission (photo, GPS, voice, map picker)
│   │   ├── dashboard.html   # Map + stats + chat widget + SSE live updates
│   │   └── briefing.html    # AI-generated city council briefing
│   └── static/
│       ├── css/style.css    # Shared responsive styles with dark mode
│       ├── manifest.json    # PWA manifest
│       ├── sw.js            # Service worker
│       ├── icon-192.svg     # PWA icon
│       ├── icon-512.svg     # PWA icon
│       └── uploads/         # Uploaded and seed images
├── seed_data/
│   ├── seed.py              # Generates demo reports using Mapillary street photos + AI classification
│   └── reclassify.py        # Re-classify existing reports with updated AI
├── tests/
│   ├── conftest.py          # Fixtures: in-memory DB, test client, mocks
│   ├── test_routes.py       # Basic route tests
│   ├── test_submit.py       # Report submission + validation tests (18 tests)
│   ├── test_classifier.py       # AI classification parsing + fallback tests
│   ├── test_dashboard.py    # Dashboard rendering tests
│   ├── test_clustering.py   # DBSCAN clustering tests
│   └── test_health_score.py # Health score + trend + accessibility tests
├── deploy.sh                # Deployment script
├── requirements.txt         # Python dependencies
├── .env.example             # Template for environment variables
└── .gitignore
```

---

## 🚀 Setup Instructions

### Prerequisites

- Python 3.10+
- A [Groq API key](https://console.groq.com/keys) (free tier works)

### 1. Clone and create virtual environment

```bash
git clone https://github.com/iheb-eddine/citypulse.git
cd citypulse
python -m venv .venv
source .venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment

```bash
cp .env.example .env
```

Edit `.env` and add your Groq API key:

```
GROQ_API_KEY=your-groq-api-key-here
```

> Without a valid key, image classification falls back to `"unclassified / medium / general"`. The app still works — AI features just degrade gracefully.

### 4. Seed demo data (optional)

```bash
python seed_data/seed.py
```

This fetches real street-level photos from Mapillary, classifies them with AI, and creates reports across Stuttgart neighborhoods. Requires `MAPILLARY_TOKEN` in `.env` (see `.env.example`).

### 5. Run the app

```bash
uvicorn app.main:app --reload
```

### 6. Open in browser

| Page | URL |
|---|---|
| Dashboard | [http://localhost:8000](http://localhost:8000) |
| Submit a report | [http://localhost:8000/submit](http://localhost:8000/submit) |
| Council briefing | [http://localhost:8000/briefing](http://localhost:8000/briefing) |

---

## 🧪 Running Tests

```bash
pip install pytest httpx
pytest tests/ -v
```

47 tests covering routes, submission validation, AI parsing/fallback, dashboard rendering, DBSCAN clustering, and health score computation.

---

## 📡 API Endpoints

### Pages (HTML)

| Method | Path | Description |
|---|---|---|
| `GET` | `/`, `/dashboard` | Interactive map dashboard with stats, chat, and live updates |
| `GET` | `/submit` | Mobile-first report submission form |
| `GET` | `/briefing` | AI-generated city council briefing |

### REST API

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/reports` | Submit a report (multipart: photo, lat, lng, description, city) |
| `GET` | `/api/reports` | List all reports for a city (JSON) |
| `GET` | `/api/reports/geojson` | GeoJSON FeatureCollection of all reports |
| `GET` | `/api/dashboard` | Dashboard stats as JSON (health score, categories, hotspots) |
| `POST` | `/api/reports/{id}/confirm` | Upvote/verify a report (auto-escalates severity at 3 confirms) |
| `PATCH` | `/api/reports/{id}/status` | Update report status (open / in_progress / resolved) |
| `POST` | `/api/chat` | AI chat — ask about city reports, trends, or news |
| `GET` | `/api/briefing` | Generate city council briefing (JSON) |
| `GET` | `/api/stream` | SSE stream — real-time new report notifications |

### POST /api/reports

**Request:** `multipart/form-data`

| Field | Type | Required | Constraints |
|---|---|---|---|
| `photo` | file | yes | JPEG, PNG, or WebP; max 10 MB |
| `latitude` | string | yes | -90 to 90 |
| `longitude` | string | yes | -180 to 180 |
| `description_text` | string | no | Citizen description (merged with AI description) |
| `city` | string | no | City key (defaults to nearest city) |

**Response (201):**

```json
{
  "id": 1,
  "photo_path": "/static/uploads/abc123.jpg",
  "latitude": 48.7758,
  "longitude": 9.1829,
  "category": "pothole",
  "severity": "high",
  "department": "roads",
  "description": "AI: Large pothole on main road | Citizen: Near the bus stop",
  "status": "open",
  "created_at": "2026-04-10 09:30:00"
}
```

---

## 📸 Screenshots

### Dashboard — Interactive map with risk zones, heatmap, and stats
![Dashboard](docs/dashboard.png)

### AI Chat Assistant — Actionable insights from report data and local news
![Chat](docs/chat.png)

### Submit Report — Photo upload, GPS, voice description, privacy badge
![Submit](docs/submit.png)

### AI Classification Result — Automatic category, severity, and department routing
![Submit Result](docs/submit-result.png)

### AI City Council Briefing — Auto-generated memo for city officials
![Briefing](docs/briefing.png)

---

## 📄 License

MIT License — see [LICENSE](LICENSE).

Built for [AlgoFest Hackathon 2026](https://algofest-hackathon26.devpost.com/) — Smart Cities & IoT track.
