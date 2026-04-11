# CityPulse — Interfaces & APIs

## REST API Endpoints

### Pages (HTML Responses)

| Method | Path | Handler | Description |
|---|---|---|---|
| `GET` | `/`, `/dashboard` | `dashboard()` | Interactive map dashboard with stats, chat, SSE |
| `GET` | `/submit` | `submit_page()` | Mobile-first report submission form |
| `GET` | `/briefing` | `briefing_page()` | AI-generated city council briefing |

### Data API

| Method | Path | Handler | Description |
|---|---|---|---|
| `POST` | `/api/reports` | `create_report()` | Submit a report (multipart/form-data) |
| `GET` | `/api/reports` | `get_reports()` | List all reports for a city (JSON array) |
| `GET` | `/api/reports/geojson` | `get_reports_geojson()` | GeoJSON FeatureCollection |
| `GET` | `/api/dashboard` | `api_dashboard()` | Dashboard stats as JSON |
| `POST` | `/api/reports/{id}/confirm` | `confirm_report()` | Upvote/verify a report |
| `PATCH` | `/api/reports/{id}/status` | `update_report_status()` | Update status (open/in_progress/resolved) |
| `POST` | `/api/chat` | `chat()` | AI chat about city reports and news |
| `GET` | `/api/briefing` | `api_briefing()` | Generate council briefing (JSON) |
| `GET` | `/api/stream` | `sse_stream()` | SSE stream for real-time updates |

## POST /api/reports — Report Submission

**Request:** `multipart/form-data`

| Field | Type | Required | Constraints |
|---|---|---|---|
| `photo` | file | Yes | JPEG, PNG, or WebP; max 10 MB; validated via magic bytes |
| `latitude` | string | Yes | Float in [-90, 90] |
| `longitude` | string | Yes | Float in [-180, 180] |
| `description_text` | string | No | Citizen description (merged with AI description) |
| `city` | string | No | City key; defaults to nearest city by coordinates |

**Success (201):**
```json
{
  "id": 1,
  "photo_path": "/static/uploads/{uuid}.jpg",
  "latitude": 48.7758,
  "longitude": 9.1829,
  "category": "pothole",
  "severity": "high",
  "department": "roads",
  "description": "AI: Large pothole | Citizen: Near bus stop",
  "status": "open",
  "created_at": "2026-04-10 09:30:00",
  "estimated_resolution_days": 9,
  "nearby_similar": [{"id": 5, "description": "..."}]
}
```

**Error Response Format:**
```json
{"error": {"code": "SCREAMING_SNAKE_CASE", "message": "Human-readable description"}}
```

**Error Codes (all 422):**

| Code | Trigger |
|---|---|
| `MISSING_FILE` | No photo field or empty filename |
| `EMPTY_FILE` | 0-byte file |
| `FILE_TOO_LARGE` | Exceeds 10 MB |
| `INVALID_FILE_TYPE` | Not JPEG/PNG/WebP (magic bytes check) |
| `INVALID_LATITUDE` | Missing, non-numeric, or outside [-90, 90] |
| `INVALID_LONGITUDE` | Missing, non-numeric, or outside [-180, 180] |

## POST /api/reports/{id}/confirm — Citizen Confirmation

**Request:** No body required.

**Response (200):**
```json
{"confirmations": 3, "severity": "high"}
```

**Behavior:** Increments `confirmations` counter. At exactly 3 confirmations, severity auto-escalates: low→medium, medium→high, high→critical, critical→critical.

## PATCH /api/reports/{id}/status — Status Update

**Request:** `application/json`
```json
{"status": "in_progress"}
```

**Valid statuses:** `open`, `in_progress`, `resolved`

## POST /api/chat — AI Chat

**Request:** `application/json`
```json
{"message": "What are the worst areas?", "city": "stuttgart"}
```

**Response:**
```json
{"response": "Hauptbahnhof has the highest concentration..."}
```

Uses Groq Llama 3.1 8B with a system prompt containing live report statistics, neighborhood breakdowns, and recent news headlines.

## GET /api/stream — Server-Sent Events

**Response:** `text/event-stream`

Each event is a JSON object:
```json
{"id": 42, "category": "pothole", "severity": "high", "neighborhood": "Hauptbahnhof", "city": "stuttgart"}
```

Events are pushed when new reports are created. Uses `asyncio.Queue` per client with max size 64; slow clients are dropped.

## External API Interfaces

### Groq API — Vision Classification

- **Endpoint:** `https://api.groq.com/openai/v1/chat/completions`
- **Model:** `meta-llama/llama-4-scout-17b-16e-instruct`
- **Auth:** Bearer token via `GROQ_API_KEY`
- **Timeout:** 30 seconds
- **Input:** Base64-encoded image + text prompt
- **Output:** JSON with `category`, `severity`, `department`, `description`

### Groq API — Text Generation (Chat, Briefing, Translation)

- **Endpoint:** Same as above
- **Model:** `llama-3.1-8b-instant`
- **Timeout:** 8-15 seconds depending on use case
- **Used for:** Chat responses, council briefings, German→English headline translation

### RSS Feeds

- **SWR:** `https://www.swr.de/~rss/swraktuell-bw-100.xml`
- **Stuttgarter Zeitung:** `https://www.stuttgarter-zeitung.de/rss/topthemen.rss.feed`
- **Timeout:** 5 seconds per feed
- **Cache:** 15-minute in-memory TTL

### Mapillary API (Seed Data Only)

- **Endpoint:** `https://graph.mapillary.com/images`
- **Auth:** `MAPILLARY_TOKEN` query parameter
- **Used by:** `seed_data/seed.py` to fetch street-level photos

## Internal Function Interfaces

### Classification Pipeline

```python
async def classify_image(image_bytes: bytes) -> dict:
    """Returns {"category", "severity", "department", "description"} or FALLBACK."""

def parse_ai_response(text: str) -> dict:
    """Parses AI JSON response. Strips markdown fences. Returns FALLBACK on any issue."""
```

### Analytics Functions

```python
def compute_health_score(reports: list) -> float:        # 0-100, severity-weighted
def compute_trend(reports: list, now=None) -> int:        # +N/-N/0 (7-day rolling)
def compute_accessibility_score(reports: list) -> float:  # 0-100, category+severity weighted
def compute_risk_scores(reports: list, city_key=None) -> list:  # Per-neighborhood risk 0-100
def run_clustering(reports: list, db: Session) -> None:   # DBSCAN, updates cluster_id in DB
```

### Database Dependency

```python
def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding SQLAlchemy session."""
```
