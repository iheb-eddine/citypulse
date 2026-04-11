# CityPulse — Codebase Information

## Project Identity

- **Name:** CityPulse
- **Tagline:** AI-Powered Urban Issue Triage
- **Purpose:** Citizens report urban issues via photo upload; AI classifies, clusters, and routes them to city departments
- **Context:** AlgoFest Hackathon 2026 — Smart Cities & IoT track
- **Live URL:** https://citypulse.help
- **Language:** Python 3.10+
- **Framework:** FastAPI
- **Database:** SQLite via SQLAlchemy ORM
- **AI Provider:** Groq API (Llama 4 Scout for vision, Llama 3.1 8B for chat/briefing/translation)

## Repository Layout

```
citypulse/
├── app/                        # Application package
│   ├── main.py                 # All routes, business logic, SSE, clustering
│   ├── models.py               # SQLAlchemy Report model
│   ├── database.py             # Engine, session factory, Base
│   ├── classifier.py           # Groq vision classification + fallback
│   ├── news.py                 # RSS fetcher with Groq translation
│   ├── templates/              # Jinja2 HTML templates
│   │   ├── submit.html         # Report submission form
│   │   ├── dashboard.html      # Map + stats + chat + SSE
│   │   └── briefing.html       # AI council briefing page
│   └── static/
│       ├── css/style.css       # Shared styles with dark mode
│       ├── manifest.json       # PWA manifest
│       ├── sw.js               # Service worker (minimal)
│       ├── icon-192.svg        # PWA icons
│       ├── icon-512.svg
│       └── uploads/            # User-uploaded + seed images
├── seed_data/
│   ├── seed.py                 # Demo data generator (Mapillary + AI classification)
│   └── reclassify.py           # Re-classify existing reports
├── tests/                      # 47 tests across 7 files
│   ├── conftest.py             # Fixtures: in-memory DB, test client, mocks
│   ├── test_routes.py          # Basic route smoke tests
│   ├── test_submit.py          # Report submission + validation (18 tests)
│   ├── test_classifier.py      # AI parsing + fallback tests
│   ├── test_dashboard.py       # Dashboard rendering tests
│   ├── test_clustering.py      # DBSCAN clustering tests
│   └── test_health_score.py    # Health score + trend + accessibility tests
├── deploy.sh                   # VPS deployment (nginx + systemd + certbot)
├── requirements.txt            # Python dependencies
├── .env.example                # Environment variable template
└── .gitignore
```

## Key Entry Points

| Entry Point | File | Purpose |
|---|---|---|
| Application startup | `app/main.py` → `lifespan()` | Creates tables, runs migrations |
| Report submission | `app/main.py` → `create_report()` | POST /api/reports |
| Dashboard render | `app/main.py` → `dashboard()` | GET / and GET /dashboard |
| AI classification | `app/classifier.py` → `classify_image()` | Groq Llama 4 Scout vision |
| Chat assistant | `app/main.py` → `chat()` | POST /api/chat |
| Briefing generation | `app/main.py` → `_generate_briefing()` | GET /api/briefing |
| News fetching | `app/news.py` → `fetch_news()` | RSS + Groq translation |
| Seed data | `seed_data/seed.py` → `main()` | Populate demo reports |
| Deployment | `deploy.sh` | VPS setup script |

## Environment Variables

| Variable | Required | Purpose |
|---|---|---|
| `GROQ_API_KEY` | Yes (for AI features) | Groq API authentication |
| `MAPILLARY_TOKEN` | No (seed only) | Mapillary street photos for seeding |
| `PEXELS_API_KEY` | No (seed only) | Pexels fallback photos for seeding |

## Technology Decisions

- **Monolith architecture:** All routes and logic in `main.py` — intentional for hackathon speed
- **Groq over Gemini:** Original spec used Gemini; evolved to Groq Llama 4 Scout for better vision results
- **SQLite:** No external DB server needed; single-file persistence
- **Folium:** Server-side map generation avoids complex JS mapping libraries
- **No JS frameworks:** Vanilla JS only, minimal client-side logic
- **DBSCAN on every dashboard load:** Acceptable at hackathon scale (~50-100 reports)
