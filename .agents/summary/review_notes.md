# CityPulse — Documentation Review Notes

## Consistency Check Results

### ✅ Resolved: Spec vs Implementation Divergences

These divergences between the original spec (`spec.md`) and the actual implementation are correctly documented:

| Area | Spec Says | Code Does | Documentation |
|---|---|---|---|
| AI Provider | Gemini 2.0 Flash via `google-genai` SDK | Groq Llama 4 Scout via `httpx` | ✅ Correctly documents Groq |
| AI SDK | `google.genai.Client` | Direct HTTP calls to `api.groq.com` | ✅ Correctly documents httpx |
| Home page | `GET /` = submit page | `GET /` = dashboard, `GET /submit` = submit | ✅ Correctly documents actual routes |
| DB columns | 10 columns | 13 columns (+city, confirmations, status) | ✅ Correctly documents all 13 |
| Heatmap | "No heatmap layer" | HeatMap plugin used | ✅ Correctly documents heatmap |
| Test file | `test_gemini.py` | `test_classifier.py` | ✅ Correctly documents actual filename |
| Features | Basic submit + dashboard | +Chat, +Briefing, +SSE, +Confirm, +Status, +GeoJSON, +Voice, +Dark mode, +PWA, +News | ✅ All documented |

### ⚠️ Cross-Document Consistency Issues

1. **None found.** All documentation files reference the same model (13 columns), same API endpoints, same Groq models, and same architecture consistently.

## Completeness Check Results

### ✅ Well-Covered Areas

- Report submission flow (validation, classification, fallback, storage)
- Dashboard rendering (clustering, scoring, map generation)
- All REST API endpoints with request/response formats
- Database schema with all constraints and enums
- External service dependencies and graceful degradation
- Deployment architecture and workflow
- Test structure and coverage areas

### ⚠️ Areas With Thin Coverage

| Area | Gap | Severity | Recommendation |
|---|---|---|---|
| `app/static/js/` directory | Directory exists but contents not analyzed | Low | Inspect JS files if client-side logic is significant |
| `app/static/css/style.css` | Mentioned but not analyzed for dark mode implementation details | Low | Document CSS custom properties and theme switching mechanism if relevant |
| Template internals | Templates listed with feature summaries but no HTML structure analysis | Low | Acceptable — templates are standard Jinja2 |
| `seed_data/reclassify.py` | Mentioned but not detailed | Low | Document purpose: re-runs AI classification on existing reports |
| Duplicate detection | `create_report()` checks for nearby similar reports within 7 days | Medium | Add to workflows.md submission flow — currently only visible in interfaces.md response format |
| `estimate_resolution_days()` | Documented in interfaces but not prominent in workflows | Low | Minor — function is simple lookup |
| Error handling for chat/briefing | Documented as "returns error message" but specific error format not detailed | Low | Chat/briefing errors return `{"response": "..."}` not the standard error format |
| Multi-worker behavior | News cache is in-memory, not shared across workers | Medium | Document that running multiple uvicorn workers would have separate caches |
| PWA service worker | `sw.js` is 3 lines — minimal/placeholder | Low | Note that PWA caching is not implemented |

### 🔍 Spec-Only Features Not in Code

These are in `spec.md` but not implemented (spec represents the original hackathon plan, code has evolved):

| Spec Feature | Status |
|---|---|
| Gemini 2.0 Flash integration | Replaced by Groq Llama 4 Scout |
| `GET /` as submit page | Changed to dashboard; submit moved to `/submit` |
| No heatmap | Heatmap added |
| 10-column schema | Expanded to 13 columns |

These are not documentation gaps — the spec is a historical artifact and the documentation correctly reflects the current implementation.

## Recommendations

1. **Consider extracting subsystems from `main.py`:** The 957-line monolith works for hackathon but would benefit from extraction if the project grows (e.g., `analytics.py` for scoring functions, `sse.py` for SSE logic)
2. **Add type hints to analytics functions:** `compute_health_score(reports: list)` could be `compute_health_score(reports: list[Report])` for better IDE support
3. **Document the `app/static/js/` directory** if it contains significant client-side logic
4. **Note in deployment docs:** Running multiple uvicorn workers would require shared caching (e.g., Redis) for news cache consistency
