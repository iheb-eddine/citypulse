# CityPulse — Workflows

## 1. Report Submission Workflow

```mermaid
flowchart TD
    A["User opens /submit"] --> B["Fill form: photo + GPS"]
    B --> C{"GPS method?"}
    C -->|"Browser geolocation"| D["Auto-fill lat/lng"]
    C -->|"Map picker"| E["Click on map"]
    C -->|"Manual entry"| F["Type coordinates"]
    D --> G["Submit form"]
    E --> G
    F --> G

    G --> H{"File present?"}
    H -->|No| ERR1["422 MISSING_FILE"]
    H -->|Yes| I{"File empty?"}
    I -->|Yes| ERR2["422 EMPTY_FILE"]
    I -->|No| J{"Size ≤ 10MB?"}
    J -->|No| ERR3["422 FILE_TOO_LARGE"]
    J -->|Yes| K{"Magic bytes = JPEG/PNG/WebP?"}
    K -->|No| ERR4["422 INVALID_FILE_TYPE"]
    K -->|Yes| L{"Lat/Lng valid?"}
    L -->|No| ERR5["422 INVALID_LATITUDE/LONGITUDE"]
    L -->|Yes| M["Strip EXIF metadata"]

    M --> N["Save as /static/uploads/{uuid}.ext"]
    N --> O["Call Groq Llama 4 Scout"]
    O -->|Success| P["Parse classification"]
    O -->|Any failure| Q["Use FALLBACK values"]
    P --> R["INSERT into SQLite"]
    Q --> R
    R --> S["Notify SSE clients"]
    S --> T["Return 201 + report JSON"]
```

## 2. Dashboard Rendering Workflow

```mermaid
flowchart TD
    A["GET /dashboard"] --> B["Load reports from SQLite"]
    B --> C{"Reports exist?"}
    C -->|No| D["Show empty state: 'No reports yet'"]
    C -->|Yes| E["Run DBSCAN clustering"]
    E --> F["Update cluster_id in DB"]
    F --> G["Apply category/severity filters"]
    G --> H["Compute metrics"]

    H --> H1["Health score (0-100)"]
    H --> H2["Trend (7-day rolling)"]
    H --> H3["Category/severity breakdown"]
    H --> H4["Top 3 hotspots"]
    H --> H5["Per-neighborhood risk scores"]
    H --> H6["Accessibility score"]

    H1 --> I["Generate Folium map"]
    I --> I1["Color-coded markers"]
    I --> I2["Heatmap overlay"]
    I --> I3["Risk zone circles"]
    I --> I4["Layer control"]

    I1 --> J["Render dashboard.html"]
    J --> K["Return HTML with map + stats"]
```

## 3. Citizen Confirmation & Auto-Escalation

```mermaid
flowchart TD
    A["POST /api/reports/{id}/confirm"] --> B["Increment confirmations"]
    B --> C{"confirmations == 3?"}
    C -->|No| D["Return current count"]
    C -->|Yes| E["Escalate severity"]
    E --> E1["low → medium"]
    E --> E2["medium → high"]
    E --> E3["high → critical"]
    E --> E4["critical → critical (no change)"]
    E1 --> D
    E2 --> D
    E3 --> D
    E4 --> D
```

## 4. AI Chat Workflow

```mermaid
flowchart TD
    A["POST /api/chat"] --> B["Parse message + city"]
    B --> C["Build report stats context"]
    C --> D["Fetch city news (RSS + translate)"]
    D --> E["Construct system prompt with data"]
    E --> F["Call Groq Llama 3.1 8B"]
    F -->|Success| G["Return AI response"]
    F -->|Failure| H["Return generic error message"]
```

**Chat context includes:** Total reports, health score, trend, category/severity breakdowns, per-category resolution rates, neighborhood risk scores, neighborhood breakdowns (top 7), and 20 most recent individual reports.

## 5. Council Briefing Workflow

```mermaid
flowchart TD
    A["GET /api/briefing"] --> B["Build briefing data"]
    B --> C{"Reports exist?"}
    C -->|No| D["Return 'No reports yet' message"]
    C -->|Yes| E{"GROQ_API_KEY set?"}
    E -->|No| F["Generate data-driven fallback briefing"]
    E -->|Yes| G["Call Groq Llama 3.1 8B"]
    G -->|Success| H["Return AI briefing"]
    G -->|Failure| F
```

The fallback briefing is generated from raw data without AI — it includes health score, top category, critical/high count, and top hotspot.

## 6. News Fetching Workflow

```mermaid
flowchart TD
    A["fetch_news(city_key)"] --> B{"Cache valid? (< 15 min)"}
    B -->|Yes| C["Return cached headlines"]
    B -->|No| D["Try RSS feeds in order"]
    D --> E{"Feed returned items?"}
    E -->|Yes| F["Filter by city keywords"]
    F --> G["Translate German → English via Groq"]
    G --> H["Cache result"]
    H --> C
    E -->|No / Error| I["Try next feed"]
    I --> E
    I -->|All feeds failed| J["Return FALLBACK_NEWS"]
```

## 7. SSE Live Updates Workflow

```mermaid
flowchart TD
    A["Client connects: GET /api/stream"] --> B["Create asyncio.Queue (max 64)"]
    B --> C["Add to sse_clients set"]
    C --> D["Wait for events"]

    E["New report created"] --> F["notify_sse_clients()"]
    F --> G["Push JSON to all queues"]
    G -->|"Queue full"| H["Drop slow client"]
    G -->|"Success"| D

    D --> I["Yield SSE event to client"]
    I --> D

    J["Client disconnects"] --> K["Remove from sse_clients"]
```

## 8. Seed Data Workflow

```mermaid
flowchart TD
    A["python seed_data/seed.py"] --> B["Create tables"]
    B --> C["Clear existing uploads + reports"]
    C --> D["Build 50 report definitions"]
    D --> D1["8 potholes near Hauptbahnhof"]
    D --> D2["5 streetlights in Bad Cannstatt"]
    D --> D3["37 scattered across Stuttgart"]

    D1 --> E["For each report"]
    D2 --> E
    D3 --> E

    E --> F["Fetch Mapillary photo"]
    F -->|"Photo found"| G["Save image"]
    F -->|"No coverage"| H["Skip report"]
    G --> I["Classify with AI"]
    I --> J["INSERT into SQLite"]
    J --> E
```

## 9. Deployment Workflow

```mermaid
flowchart TD
    A["Run deploy.sh on VPS"] --> B["Install system deps"]
    B --> C["Create venv + install requirements"]
    C --> D["Seed demo data"]
    D --> E["Create systemd service"]
    E --> F["Configure nginx reverse proxy"]
    F --> G["Obtain SSL cert via certbot"]
    G --> H["App live at citypulse.help"]
```
