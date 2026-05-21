"""Chain-of-Thought severity reasoning — rule-based, deterministic."""

from app.config import SEVERITY_WEIGHTS, ACCESSIBILITY_WEIGHTS

KEYWORDS = {"danger", "hazard", "collapse", "exposed", "blocked",
            "urgent", "emergency", "spreading", "unstable", "sparking"}


def generate_reasoning(report, nearby_count: int) -> dict:
    steps = [
        _severity_baseline(report),
        _spatial_density(nearby_count),
        _time_of_day(report),
        _description_keywords(report),
        _accessibility_impact(report),
    ]
    neg = sum(1 for s in steps if s["impact"] == "negative")
    pos = sum(1 for s in steps if s["impact"] == "positive")
    consistent = _check_consistency(report.severity, neg, pos)
    return {
        "report_id": report.id,
        "severity": report.severity,
        "reasoning_steps": steps,
        "consistent": consistent,
        "conclusion": _conclusion(report.severity, neg, pos, consistent),
    }


def _severity_baseline(report):
    w = SEVERITY_WEIGHTS.get(report.severity, 2)
    if w >= 5:
        impact, obs = "negative", f"Critical severity carries maximum urgency weight ({w}/5)"
    elif w >= 3:
        impact, obs = "negative", f"High severity carries elevated urgency weight ({w}/5)"
    elif w >= 2:
        impact, obs = "neutral", f"Medium severity carries standard urgency weight ({w}/5)"
    else:
        impact, obs = "positive", f"Low severity carries minimal urgency weight ({w}/5)"
    return {"factor": "severity_baseline", "observation": obs, "impact": impact}


def _spatial_density(nearby_count):
    if nearby_count == 0:
        return {"factor": "spatial_density", "observation": "Isolated incident — no similar reports nearby", "impact": "positive"}
    if nearby_count <= 2:
        return {"factor": "spatial_density", "observation": f"{nearby_count} similar report(s) within 200m in the last 7 days", "impact": "neutral"}
    return {"factor": "spatial_density", "observation": f"{nearby_count} similar reports within 200m in the last 7 days indicates a cluster", "impact": "negative"}


def _time_of_day(report):
    h = report.created_at.hour
    if h >= 22 or h < 6:
        return {"factor": "time_of_day", "observation": f"Reported at nighttime ({h:02d}:00) — reduced visibility, safety concern", "impact": "negative"}
    return {"factor": "time_of_day", "observation": f"Reported during daytime ({h:02d}:00) — standard visibility", "impact": "neutral"}


def _description_keywords(report):
    desc_lower = (report.description or "").lower()
    found = sorted(k for k in KEYWORDS if k in desc_lower)
    if found:
        return {"factor": "description_keywords", "observation": f"Description contains high-risk keyword(s): {', '.join(found)}", "impact": "negative"}
    return {"factor": "description_keywords", "observation": "No high-risk keywords detected in description", "impact": "neutral"}


def _accessibility_impact(report):
    w = ACCESSIBILITY_WEIGHTS.get(report.category, 1)
    cat = report.category
    if w >= 2.5:
        return {"factor": "accessibility_impact", "observation": f"{cat} has high accessibility impact (weight {w}/3)", "impact": "negative"}
    if w >= 1.5:
        return {"factor": "accessibility_impact", "observation": f"{cat} has moderate accessibility impact (weight {w}/3)", "impact": "neutral"}
    return {"factor": "accessibility_impact", "observation": f"{cat} has minimal accessibility impact (weight {w}/3)", "impact": "positive"}


def _check_consistency(severity, neg, pos):
    if severity in ("high", "critical"):
        return neg > pos
    if severity == "low":
        return pos >= neg
    return True  # medium always consistent


def _conclusion(severity, neg, pos, consistent):
    if not consistent:
        return "Factors suggest severity may warrant re-evaluation"
    if neg > pos:
        return f"{neg} of 5 factors indicate elevated severity, consistent with {severity} classification"
    if pos > neg:
        return f"{pos} of 5 factors indicate reduced severity, consistent with {severity} classification"
    return f"Factors are balanced, consistent with {severity} classification"
