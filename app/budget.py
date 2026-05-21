"""LP Budget Optimizer — anomaly-weighted proportional allocation with linprog efficiency scoring."""

from scipy.optimize import linprog
from sqlalchemy.orm import Session

from app.anomaly import get_state
from app.config import SEVERITY_WEIGHTS, CITIES, get_city, neighborhood_for_coords
from app.models import Report

DEPARTMENTS = ["roads", "electrical", "sanitation", "water", "parks", "general"]
DEFAULT_BUDGET = 100_000.0
MIN_ALLOCATION_FRACTION = 0.05


def _compute_department_weights(db: Session, city: str) -> dict[str, float]:
    weights = {d: 0.0 for d in DEPARTMENTS}
    reports = db.query(Report).filter(Report.city == city, Report.status != "resolved").all()
    if not reports:
        return weights

    # Collect all anomaly rates for the city to compute mean/std
    _, cfg = get_city(city)
    rates = []
    for nh_tuple in cfg["neighborhoods"]:
        state = get_state(city, nh_tuple[4])
        if state:
            rates.append(state["alpha"] / state["beta"])

    mean_rate = sum(rates) / len(rates) if rates else 0.0
    std_rate = (sum((r - mean_rate) ** 2 for r in rates) / len(rates)) ** 0.5 if rates else 0.0

    for r in reports:
        factor = 1.0
        if std_rate > 0:
            nh = neighborhood_for_coords(r.latitude, r.longitude, city)
            state = get_state(city, nh)
            if state:
                rate = state["alpha"] / state["beta"]
                factor = 1 + max(0, (rate - mean_rate) / std_rate)
                factor = min(factor, 5.0)  # Clamp to prevent domination
        weights[r.department] += SEVERITY_WEIGHTS[r.severity] * factor

    return weights


def _solve_lp(weights: dict[str, float], total_budget: float) -> dict:
    floor = MIN_ALLOCATION_FRACTION * total_budget
    sum_w = sum(weights.values())

    if sum_w == 0:
        alloc = {d: total_budget / len(DEPARTMENTS) for d in DEPARTMENTS}
        return {"allocations": alloc, "impact_score": 0, "department_weights": {d: 0.0 for d in DEPARTMENTS}}

    distributable = total_budget - len(DEPARTMENTS) * floor
    norm_w = {d: weights[d] / sum_w for d in DEPARTMENTS}
    allocations = {d: floor + distributable * norm_w[d] for d in DEPARTMENTS}

    # LP for theoretical maximum (corner solution)
    c = [-norm_w[d] for d in DEPARTMENTS]
    bounds = [(floor, None) for _ in DEPARTMENTS]
    A_eq = [[1.0] * len(DEPARTMENTS)]
    b_eq = [total_budget]

    result = linprog(c, A_eq=A_eq, b_eq=b_eq, bounds=bounds, method="highs")

    if not result.success:
        return {"allocations": allocations, "impact_score": None, "department_weights": norm_w}

    prop_obj = sum(norm_w[d] * allocations[d] for d in DEPARTMENTS)
    lp_obj = -result.fun
    impact_score = prop_obj / lp_obj if lp_obj > 0 else 0

    return {"allocations": allocations, "impact_score": round(impact_score, 4), "department_weights": norm_w}


def optimize_budget(city: str, total_budget: float, db: Session) -> dict:
    weights = _compute_department_weights(db, city)
    result = _solve_lp(weights, total_budget)
    result["city"] = city
    result["total_budget"] = total_budget
    return result
