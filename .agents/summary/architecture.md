# CityPulse — Architecture

## System Architecture

```mermaid
graph TB
    subgraph Client["Browser (Mobile-First)"]
        Submit["Submit Page<br>/submit"]
        Dashboard["Dashboard<br>/ or /dashboard"]
        Briefing["Briefing Page<br>/briefing"]
        SSEClient["SSE Listener"]
    end

    subgraph Server["FastAPI Server (app/main.py)"]
        Routes["Route Handlers"]
        Clustering["DBSCAN Clustering"]
        HealthScore["Health Score Engine"]
        RiskScores["Risk Score Engine"]
        MapGen["Folium Map Generator"]
        ChatEngine["Chat Engine"]
        BriefingGen["Briefing Generator"]
        SSEEngine["SSE Broadcaster"]
        MetadataStrip["EXIF Stripper (Pillow)"]
    end

    subgraph External["External Services"]
        GroqVision["Groq API<br>Llama 4 Scout<br>(Vision Classification)"]
        GroqChat["Groq API<br>Llama 3.1 8B<br>(Chat/Briefing/Translation)"]
        RSS["RSS Feeds<br>(SWR, Stuttgarter Zeitung)"]
        Mapillary["Mapillary API<br>(Seed Photos)"]
    end

    subgraph Storage["Local Storage"]
        SQLite["SQLite DB<br>citypulse.db"]
        Uploads["static/uploads/<br>Photo Files"]
    end

    Submit -->|"POST /api/reports<br>multipart/form-data"| Routes
    Dashboard -->|"GET /"| Routes
    Briefing -->|"GET /briefing"| Routes
    SSEClient -->|"GET /api/stream"| SSEEngine

    Routes --> MetadataStrip
    MetadataStrip --> Uploads
    Routes -->|"classify_image()"| GroqVision
    Routes --> SQLite
    Routes --> Clustering
    Clustering --> HealthScore
    HealthScore --> RiskScores
    RiskScores --> MapGen
    ChatEngine --> GroqChat
    ChatEngine --> RSS
    BriefingGen --> GroqChat
    Routes --> SSEEngine
```

## Design Pattern: Monolith with Module Extraction

The application follows a monolith pattern with selective module extraction:

| Module | Responsibility | Why Extracted |
|---|---|---|
| `main.py` | Routes, business logic, SSE, map generation | Central orchestrator — intentionally monolithic |
| `classifier.py` | AI vision classification + response parsing | Isolates external API dependency and fallback logic |
| `news.py` | RSS fetching + translation | Isolates external data source with caching |
| `models.py` | SQLAlchemy ORM model | Standard separation of data model |
| `database.py` | Engine, session, Base | Standard separation of DB infrastructure |

## Request Flow: Report Submission

```mermaid
sequenceDiagram
    participant B as Browser
    participant F as FastAPI
    participant V as Validator
    participant P as Pillow
    participant G as Groq API
    participant D as SQLite
    participant S as SSE Clients

    B->>F: POST /api/reports (photo + GPS)
    F->>V: Validate file (magic bytes, size)
    V-->>F: OK / Error 422
    F->>V: Validate lat/lng range
    V-->>F: OK / Error 422
    F->>P: Strip EXIF metadata
    P-->>F: Clean image bytes
    F->>F: Save to /static/uploads/{uuid}.ext
    F->>G: Classify image (Llama 4 Scout)
    alt Success
        G-->>F: {category, severity, department, description}
    else Any failure
        F->>F: Use FALLBACK values
    end
    F->>D: INSERT report
    F->>S: Notify SSE clients
    F-->>B: 201 Created + report JSON
```

## Request Flow: Dashboard

```mermaid
sequenceDiagram
    participant B as Browser
    participant F as FastAPI
    participant D as SQLite
    participant C as DBSCAN
    participant M as Folium

    B->>F: GET /dashboard
    F->>D: Load all reports (filtered by city)
    F->>C: Run DBSCAN clustering
    C->>D: Update cluster_id on reports
    F->>F: Compute health score, trend, risk scores
    F->>M: Generate map with markers + heatmap + risk zones
    F-->>B: HTML with embedded map + stats panel
```

## AI Integration Architecture

```mermaid
graph LR
    subgraph Vision["Vision Classification"]
        Photo["Photo Bytes"] --> Encode["Base64 Encode"]
        Encode --> Scout["Groq Llama 4 Scout<br>meta-llama/llama-4-scout-17b-16e-instruct"]
        Scout --> Parse["parse_ai_response()"]
        Parse -->|Valid JSON| Result["Classification Result"]
        Parse -->|Any failure| Fallback["FALLBACK Dict"]
    end

    subgraph Text["Text Generation"]
        Chat["Chat Request"] --> LLM["Groq Llama 3.1 8B<br>llama-3.1-8b-instant"]
        BriefReq["Briefing Request"] --> LLM
        TransReq["Translation Request"] --> LLM
    end
```

All Groq API calls use `httpx.AsyncClient` with explicit timeouts. Every call has a fallback path — the app never returns 500 to users due to AI failures.

## Data Flow: Clustering → Dashboard

```mermaid
graph TD
    Reports["All Reports<br>(lat, lng pairs)"] --> DBSCAN["DBSCAN<br>eps=0.003, min_samples=3"]
    DBSCAN --> Labels["Cluster Labels<br>-1 = noise, 0+ = cluster"]
    Labels --> Update["Update cluster_id<br>in SQLite"]
    Update --> Hotspots["compute_hotspots()<br>Top 3 clusters by count"]
    Update --> Risk["compute_risk_scores()<br>Per-neighborhood risk 0-100"]
    Update --> Health["compute_health_score()<br>Severity-weighted 0-100"]
    Hotspots --> Stats["Stats Panel"]
    Risk --> MapOverlay["Risk Zone Circles<br>on Folium Map"]
    Health --> Stats
```

## Deployment Architecture

```mermaid
graph LR
    Internet["Internet"] --> Nginx["Nginx<br>:80/:443"]
    Nginx -->|"proxy_pass"| Uvicorn["Uvicorn<br>127.0.0.1:8000"]
    Uvicorn --> App["FastAPI App"]
    App --> DB["SQLite<br>/opt/citypulse/citypulse.db"]
    App --> Files["Static Files<br>/opt/citypulse/app/static/"]

    Certbot["Certbot"] -.->|"SSL cert"| Nginx
    Systemd["systemd"] -.->|"manages"| Uvicorn
```

- Domain: `citypulse.help`
- Deploy script: `deploy.sh` (run on VPS as root)
- Process manager: systemd (`citypulse.service`)
- Reverse proxy: nginx with SSL via certbot
- Max upload: 12MB (nginx) / 10MB (app validation)
