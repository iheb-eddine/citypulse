# AGENTS.md — CityPulse

> AI-Powered Urban Issue Triage. Citizens upload photos of urban issues → AI classifies and routes them → dashboard shows clusters and city health.

## Table of Contents

- [Architecture Overview](#architecture-overview) — System design, AI integration, data flow
- [Directory Map](#directory-map) — Where to find things
- [Key Entry Points](#key-entry-points) — Start here for any task
- [Data Model](#data-model) — Single table, 13 columns, enum constraints
- [API Surface](#api-surface) — All endpoints at a glance
- [AI Integration](#ai-integration) — Groq models, fallback behavior, prompt locations
- [Patterns & Conventions](#patterns--conventions) — Deviations from defaults, gotchas
- [Configuration](#configuration) — Environment variables, city config
- [Testing](#testing) — Test structure and mocking strategy
- [Deployment](#deployment) — VPS with nginx + systemd
- [Detailed Documentation](#detailed-documentation) — Links to full docs in `.agents/summary/`
- [Custom Instructions](#custom-instructions) — Human/agent-maintained conventions

---

## Architecture Overview
<!-- tags: architecture, design, system -->

FastAPI monolith. All routes and business logic live in `app/main.py`. Two modules extracted for external API isolation:

```
app/main.py          → Routes, clustering, scoring, SSE, map generation, chat, briefing
app/classifier.py    → Groq Llama 4 Scout vision classification + fallback
app/news.py          → RSS fetcher + Groq translation + 15-min cache
app/models.py        → SQLAlchemy Report model (single table)
app/database.py      → SQLite engine + session factory
```

**Data flow:** Photo upload → EXIF strip → Groq vision classify (or FALLBACK) → SQLite insert → SSE notify → Dashboard loads → DBSCAN cluster → Folium map render.

**AI models:**
- `meta-llama/llama-4-scout-17b-16e-instruct` — image classification (30s timeout)
- `llama-3.1-8b-instant` — chat (10s), briefing (15s), news translation (8s)

All AI calls go through `httpx.AsyncClient` to `api.groq.com`. Every call has a fallback — the app never returns 500 due to AI failure.

---

## Directory Map
<!-- tags: navigation, structure -->

```
citypulse/
├── app/
│   ├── main.py              # ALL routes + business logic (monolith)
│   ├── classifier.py        # Groq vision classification + parse + fallback
│   ├── news.py              # RSS fetch + translate + cache
│   ├── models.py            # Report ORM model
│   ├── database.py          # Engine, session, Base
│   ├── templates/
│   │   ├── submit.html      # Photo upload + GPS + voice input
│   │   ├── dashboard.html   # Map + stats + chat widget + SSE
│   │   └── briefing.html    # AI council briefing
│   └── static/
│       ├── css/style.css    # Shared styles + dark mode
│       ├── manifest.json    # PWA manifest
│       ├── sw.js            # Service worker (minimal)
│       └── uploads/         # User photos (UUID-named)
├── seed_data/
│   ├── seed.py              # Demo data: Mapillary photos + AI classification
│   └── reclassify.py        # Re-classify existing reports
├── tests/                   # 47 tests, 7 files
│   ├── conftest.py          # In-memory DB, test client, mock fixtures
│   ├── test_submit.py       # 18 submission + validation tests
│   ├── test_classifier.py   # AI parsing + fallback tests
│   ├── test_clustering.py   # DBSCAN tests
│   ├── test_health_score.py # Scoring + trend tests
│   ├── test_dashboard.py    # Dashboard rendering tests
│   └── test_routes.py       # Basic route smoke tests
├── deploy.sh                # VPS deployment (nginx + systemd + certbot)
├── requirements.txt
└── .env.example
```

---

## Key Entry Points
<!-- tags: navigation, entry-points -->

| Task | Start Here |
|---|---|
| Add/modify an API endpoint | `app/main.py` — all routes are here |
| Change AI classification | `app/classifier.py` → `classify_image()`, `parse_ai_response()` |
| Modify the data model | `app/models.py` → `Report` class, then check `lifespan()` in `main.py` for migrations |
| Change dashboard metrics | `app/main.py` → `compute_health_score()`, `compute_trend()`, `compute_risk_scores()` |
| Modify map rendering | `app/main.py` → `dashboard()` function (Folium map generation) |
| Change chat behavior | `app/main.py` → `CHAT_SYSTEM_PROMPT`, `_build_report_stats()`, `chat()` |
| Add a new city | `app/main.py` → `CITIES` dict (add config block with neighborhoods, bbox, keywords, feeds) |
| Modify news fetching | `app/news.py` → `fetch_news()` |
| Run tests | `pytest tests/ -v` |
| Seed demo data | `python seed_data/seed.py` (requires `MAPILLARY_TOKEN`) |
| Deploy | `deploy.sh` on VPS as root |

---

## Data Model
<!-- tags: database, schema, model -->

Single table `reports` with 13 columns. SQLAlchemy model in `app/models.py`.

| Column | Type | Key Info |
|---|---|---|
| `id` | INTEGER | PK, autoincrement |
| `photo_path` | TEXT | `/static/uploads/{uuid}.{ext}` |
| `latitude` | FLOAT | CHECK [-90, 90] |
| `longitude` | FLOAT | CHECK [-180, 180] |
| `city` | TEXT | Default `'stuttgart'` |
| `category` | TEXT | `pothole\|streetlight\|graffiti\|flooding\|dumping\|sign\|other\|unclassified` |
| `severity` | TEXT | `low\|medium\|high\|critical` |
| `department` | TEXT | `roads\|electrical\|sanitation\|water\|parks\|general` |
| `description` | TEXT | AI-generated, optionally merged with citizen text |
| `cluster_id` | INTEGER | Nullable. Set by DBSCAN on dashboard load |
| `confirmations` | INTEGER | Default 0. Auto-escalates severity at 3 |
| `status` | TEXT | `open\|in_progress\|resolved` |
| `created_at` | DATETIME | Default CURRENT_TIMESTAMP |

**Migrations:** Handled in `lifespan()` via `ALTER TABLE` + `sa_inspect()` column checks. Columns added post-initial: `confirmations`, `status`, `city`.

**Index:** `idx_reports_created_at` on `created_at`.

---

## API Surface
<!-- tags: api, endpoints, routes -->

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/`, `/dashboard` | Dashboard (HTML) |
| `GET` | `/submit` | Submit form (HTML) |
| `GET` | `/briefing` | Briefing page (HTML) |
| `POST` | `/api/reports` | Create report (multipart: photo + GPS) |
| `GET` | `/api/reports` | List reports (JSON) |
| `GET` | `/api/reports/geojson` | GeoJSON export |
| `GET` | `/api/dashboard` | Dashboard stats (JSON) |
| `POST` | `/api/reports/{id}/confirm` | Upvote report |
| `PATCH` | `/api/reports/{id}/status` | Change status |
| `POST` | `/api/chat` | AI chat |
| `GET` | `/api/briefing` | Generate briefing (JSON) |
| `GET` | `/api/stream` | SSE live updates |

**Error format:** `{"error": {"code": "SCREAMING_SNAKE_CASE", "message": "..."}}`

**Report submission error codes (422):** `MISSING_FILE`, `EMPTY_FILE`, `FILE_TOO_LARGE`, `INVALID_FILE_TYPE`, `INVALID_LATITUDE`, `INVALID_LONGITUDE`

---

## AI Integration
<!-- tags: ai, groq, classification, fallback -->

**Provider:** Groq API via `httpx` (not SDK). Auth: `GROQ_API_KEY` env var.

**Vision classification** (`app/classifier.py`):
- Model: `meta-llama/llama-4-scout-17b-16e-instruct`
- Input: base64-encoded image + structured prompt
- Output: JSON with `category`, `severity`, `department`, `description`
- Validation: checks enum membership, strips markdown fences
- Fallback on ANY failure: `{"category": "unclassified", "severity": "medium", "department": "general", "description": "Classification pending — AI service unavailable"}`

**Text generation** (chat, briefing, translation):
- Model: `llama-3.1-8b-instant`
- Chat: system prompt with live report stats + news headlines
- Briefing: formal council memo prompt, with data-driven fallback if AI fails
- Translation: German RSS headlines → English

**Critical pattern:** The app NEVER surfaces AI errors to users. Every AI call path has a fallback that returns usable data.

---

## Patterns & Conventions
<!-- tags: patterns, gotchas, conventions -->

**Deviations from spec.md:** The original spec references Gemini 2.0 Flash and `google-genai` SDK. The implementation uses Groq Llama 4 Scout via direct HTTP. The spec is a historical artifact — always trust the code.

**File validation:** Uses magic bytes (binary headers), not file extensions. See `detect_file_type()` in `main.py`.

**EXIF stripping:** All uploaded photos are re-saved through Pillow to strip metadata. See `strip_metadata()` in `main.py`.

**Clustering optimization:** `run_clustering()` skips re-clustering if report count hasn't changed (module-level `_last_cluster_count`). Resets on server restart.

**Circular import:** `news.py` imports `CITIES` from `main.py` at call time (inside `fetch_news()`), not at module level.

**SSE:** Uses `asyncio.Queue` per client (max 64 items). Slow clients are dropped silently.

**Severity escalation:** At exactly 3 citizen confirmations, severity bumps up one level (low→medium→high→critical). Happens in `confirm_report()`.

**Multi-city:** `CITIES` dict in `main.py` defines city configs. Currently only Stuttgart. Adding a city = adding a dict entry with `name`, `lat`, `lng`, `zoom`, `neighborhoods`, `bbox`, `news_keywords`, `rss_feeds`.

**No auth:** Public submission, no user accounts. Intentional for hackathon scope.

---

## Configuration
<!-- tags: config, environment -->

| Variable | Required | Purpose |
|---|---|---|
| `GROQ_API_KEY` | For AI features | Groq API auth. Without it, classification falls back; chat/briefing degrade |
| `MAPILLARY_TOKEN` | Seed only | Street photos for demo data |
| `PEXELS_API_KEY` | Seed only | Fallback photos for demo data |

**DB:** `citypulse.db` in project root (hardcoded in `database.py`).

**Upload dir:** `app/static/uploads/` (created automatically).

---

## Testing
<!-- tags: testing, tests -->

47 tests across 7 files. Run: `pytest tests/ -v`

**Mocking strategy:**
- DB: In-memory SQLite via `StaticPool` (function-scoped)
- FastAPI: `TestClient` with `dependency_overrides` for `get_db`
- AI: Mock `httpx.AsyncClient.post` for Groq API calls
- Files: `BytesIO` with minimal valid JPEG/PNG bytes from `conftest.py`

**Test fixtures** (`tests/conftest.py`): `db_session`, `test_client`, `mock_ai_success`, `mock_ai_timeout`, `sample_image`, `sample_png`

---

## Deployment
<!-- tags: deployment, production -->

- **Domain:** `citypulse.help`
- **Server:** VPS at `/opt/citypulse`
- **Stack:** nginx (reverse proxy + SSL) → uvicorn (ASGI) → FastAPI
- **Process:** systemd service `citypulse.service`
- **SSL:** certbot with nginx plugin
- **Script:** `deploy.sh` (run on server as root)
- **Upload limit:** 12MB nginx / 10MB app validation

---

## Detailed Documentation
<!-- tags: docs, reference -->

Full documentation in `.agents/summary/`:

| File | Content |
|---|---|
| `index.md` | Documentation index — start here for deep dives |
| `codebase_info.md` | Project identity, layout, entry points, tech decisions |
| `architecture.md` | System design, request flows, deployment topology (Mermaid diagrams) |
| `components.md` | Module-by-module breakdown with subsystem details |
| `interfaces.md` | All API endpoints with request/response formats and error codes |
| `data_models.md` | Database schema, ORM model, enum values, in-memory structures |
| `workflows.md` | Step-by-step flows for all features (Mermaid diagrams) |
| `dependencies.md` | Python packages, external services, graceful degradation |
| `review_notes.md` | Documentation quality review and recommendations |

---

## Custom Instructions
<!-- This section is for human and agent-maintained operational knowledge.
     Add repo-specific conventions, gotchas, and workflow rules here.
     This section is preserved exactly as-is when re-running codebase-summary. -->
