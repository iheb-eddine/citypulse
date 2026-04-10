# 🏙️ CityPulse — AI-Powered Urban Issue Triage

> **Turn every citizen's phone into a smart city sensor.**

🌐 **[citypulse.help](https://citypulse.help)**

[![Built for AlgoFest Hackathon 2026](https://img.shields.io/badge/AlgoFest_2026-Smart_Cities_%26_IoT-1a73e8)](#)

Citizens snap a photo of an urban issue — pothole, broken streetlight, graffiti — and CityPulse does the rest. AI classifies the problem, routes it to the right city department, and clusters hotspots on a live dashboard so resources go where they're needed most.

**Why CityPulse?**
- **Zero infrastructure** — works in any mobile browser, no app install
- **Real-time AI classification** — Groq (Llama 4 Scout) vision API categorizes issues instantly
- **Spatial clustering** — DBSCAN groups nearby reports into actionable hotspots
- **City health score** — a single KPI for urban wellbeing, updated on every dashboard load

---

## How It Works

1. **Upload** — Citizen takes a photo and shares GPS location via mobile browser
2. **AI Classify** — Gemini 2.0 Flash analyzes the image → category, severity, department
3. **Store** — Report saved to SQLite with coordinates and classification
4. **Cluster** — Dashboard runs DBSCAN on all report coordinates (on-demand, every page load)
5. **Visualize** — Interactive Folium/Leaflet map with color-coded markers, health score, and hotspot detection

---

## Tech Stack

| Technology | Role |
|---|---|
| **FastAPI** | Web framework and API |
| **SQLite + SQLAlchemy** | Database and ORM |
| **Google Gemini 2.0 Flash** | Vision AI for image classification |
| **scikit-learn (DBSCAN)** | Geospatial clustering of reports |
| **Folium / Leaflet.js** | Interactive map rendering |
| **Jinja2** | Server-side HTML templates |
| **NumPy** | Coordinate array processing |
| **Vanilla HTML/CSS/JS** | Mobile-responsive frontend (no framework) |
| **Pillow** | Seed data only — generates placeholder images |

---

## Architecture

```
┌─────────────┐     POST /api/reports      ┌──────────────┐
│   Mobile     │ ──── photo + GPS ────────▶ │   FastAPI     │
│   Browser    │                            │   Server      │
└─────────────┘                            └──────┬───────┘
                                                   │
                                    ┌──────────────┼──────────────┐
                                    ▼              ▼              │
                             ┌────────────┐ ┌───────────┐        │
                             │ Gemini 2.0 │ │  SQLite   │        │
                             │ Flash API  │ │  Database │        │
                             └─────┬──────┘ └─────┬─────┘        │
                                   │              │              │
                                   │  category,   │              │
                                   │  severity,   │              │
                                   │  department   │              │
                                   └──────┬───────┘              │
                                          ▼                      │
                                   ┌─────────────┐              │
                                   │   Report     │              │
                                   │   Stored     │              │
                                   └─────────────┘              │
                                                                 │
┌─────────────┐     GET /dashboard         ┌──────────────┐      │
│   Browser    │ ◀──── map + stats ─────── │  Dashboard   │ ◀────┘
└─────────────┘                            │  Route       │
                                           └──────┬───────┘
                                                   │
                                    ┌──────────────┼──────────────┐
                                    ▼              ▼              ▼
                             ┌────────────┐ ┌───────────┐ ┌───────────┐
                             │  DBSCAN    │ │  Health   │ │  Folium   │
                             │  Clustering│ │  Score    │ │  Map Gen  │
                             └────────────┘ └───────────┘ └───────────┘
```

---

## Project Structure

```
citypulse/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI routes, clustering, health score
│   ├── database.py          # SQLAlchemy engine and session
│   ├── models.py            # Report model with constraints
│   ├── gemini.py            # Gemini API client + fallback logic
│   ├── templates/
│   │   ├── submit.html      # Mobile-first report submission form
│   │   └── dashboard.html   # Map + stats dashboard
│   └── static/
│       ├── css/style.css    # Shared responsive styles
│       └── uploads/         # Uploaded and seed images
├── seed_data/
│   └── seed.py              # Generates 50 demo reports across Stuttgart
├── tests/
│   ├── conftest.py          # Fixtures: in-memory DB, test client, mocks
│   ├── test_routes.py       # Basic route tests
│   ├── test_submit.py       # Report submission + validation tests
│   ├── test_gemini.py       # Gemini parsing + fallback tests
│   ├── test_dashboard.py    # Dashboard rendering tests
│   ├── test_clustering.py   # DBSCAN clustering tests
│   └── test_health_score.py # Health score + trend tests
├── requirements.txt         # Python dependencies
├── .env.example             # Template for environment variables
└── .gitignore
```

---

## Setup Instructions

### Prerequisites

- Python 3.10+
- A [Google Gemini API key](https://aistudio.google.com/apikey) (free tier works)

### 1. Clone and create virtual environment

```bash
git clone <repo-url> citypulse
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

Edit `.env` and add your Gemini API key:

```
GEMINI_API_KEY=your-api-key-here
```

> Without a valid key, image classification falls back to `"unclassified / medium / general"`. The app still works.

### 4. Seed demo data (optional)

The seed script requires Pillow for generating placeholder images:

```bash
pip install Pillow
python seed_data/seed.py
```

This creates 50 reports across Stuttgart neighborhoods with clustered hotspots.

### 5. Run the app

```bash
uvicorn app.main:app --reload
```

### 6. Open in browser

| Page | URL |
|---|---|
| Submit a report | [http://localhost:8000](http://localhost:8000) |
| City dashboard | [http://localhost:8000/dashboard](http://localhost:8000/dashboard) |

---

## Running Tests

```bash
pip install pytest httpx
pytest tests/ -v
```

47 tests covering routes, submission validation, Gemini parsing, dashboard rendering, DBSCAN clustering, and health score computation.

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | Report submission form (HTML) |
| `GET` | `/dashboard` | Interactive map + stats panel (HTML) |
| `POST` | `/api/reports` | Submit a report (multipart: photo, latitude, longitude) |
| `GET` | `/api/reports` | List reports (stub — returns `[]`) |

### POST /api/reports

**Request:** `multipart/form-data`

| Field | Type | Required | Constraints |
|---|---|---|---|
| `photo` | file | yes | JPEG, PNG, or WebP; max 10 MB |
| `latitude` | string | yes | -90 to 90 |
| `longitude` | string | yes | -180 to 180 |

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
  "description": "Large pothole on main road",
  "created_at": "2026-04-10 09:30:00"
}
```

---

## Key Features

- **AI-Powered Classification** — Gemini 2.0 Flash vision API categorizes issues into 7 types, 4 severity levels, and 6 city departments
- **Geospatial Clustering** — DBSCAN (eps=0.003, min_samples=3) groups nearby reports into hotspots for targeted response
- **City Health Score** — Weighted severity metric (0–100) computed from all active reports
- **Weekly Trend** — Compares this week's report count to last week's
- **Interactive Map** — Folium/Leaflet map with color-coded markers (green/orange/red by severity) and popup details
- **Mobile-Responsive** — Submit reports from any phone browser; dashboard stacks on small screens
- **Graceful AI Fallback** — If Gemini is unavailable or returns invalid data, reports are saved as "unclassified" with medium severity

---

## Screenshots

> _Screenshots coming soon — seed the database and visit `/dashboard` to see the app in action._

---

## License

Built for [AlgoFest Hackathon 2026](https://algofest.dev) — Smart Cities & IoT track.
