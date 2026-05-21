"""Bayesian Anomaly Detection — Poisson-Gamma conjugate prior per neighborhood."""

import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from math import exp, sqrt

# Configuration from environment
Z_THRESHOLD = float(os.environ.get("ANOMALY_Z_THRESHOLD", "2.0"))
DECAY_RATE = float(os.environ.get("ANOMALY_DECAY_RATE", "0.01"))
MIN_WINDOW_HOURS = float(os.environ.get("ANOMALY_MIN_WINDOW_HOURS", "0.0167"))
MIN_OBSERVATIONS = float(os.environ.get("ANOMALY_MIN_OBSERVATIONS", "5.0"))
COOLDOWN_SECONDS = int(os.environ.get("ANOMALY_COOLDOWN_SECONDS", "300"))
ALPHA_FLOOR = float(os.environ.get("ANOMALY_ALPHA_FLOOR", "0.5"))
BETA_FLOOR = float(os.environ.get("ANOMALY_BETA_FLOOR", "0.5"))


@dataclass
class NeighborhoodState:
    alpha: float = 1.0
    beta: float = 1.0
    current_count: int = 0
    last_update: float = field(default_factory=time.time)
    last_alert: float = 0.0


class BayesianAnomalyDetector:
    def __init__(self) -> None:
        self._states: dict[tuple[str, str], NeighborhoodState] = {}

    def _get_or_create_state(self, city: str, neighborhood: str) -> NeighborhoodState:
        key = (city, neighborhood)
        if key not in self._states:
            self._states[key] = NeighborhoodState()
        return self._states[key]

    def on_report(self, city: str, neighborhood: str) -> None:
        state = self._get_or_create_state(city, neighborhood)
        state.current_count += 1

        now = time.time()
        elapsed_hours = (now - state.last_update) / 3600.0
        if elapsed_hours < MIN_WINDOW_HOURS:
            return

        # 1. Apply exponential decay
        decay_factor = exp(-elapsed_hours * DECAY_RATE)
        state.alpha = max(ALPHA_FLOOR, state.alpha * decay_factor)
        state.beta = max(BETA_FLOOR, state.beta * decay_factor)

        # 2. Compute z-score BEFORE posterior update
        posterior_mean = state.alpha / state.beta
        posterior_std = sqrt(state.alpha) / state.beta
        observed_rate = state.current_count / elapsed_hours
        z_score = (observed_rate - posterior_mean) / posterior_std

        # 3. Credible interval (95%, normal approximation)
        lower = max(0.0, posterior_mean - 1.96 * posterior_std)
        upper = posterior_mean + 1.96 * posterior_std

        # 4. Update posterior
        state.alpha += state.current_count
        state.beta += elapsed_hours

        # 5. Reset window
        state.current_count = 0
        state.last_update = now

        # 6. Check anomaly (post-update alpha for min_observations)
        if z_score > Z_THRESHOLD and state.alpha > MIN_OBSERVATIONS:
            if now - state.last_alert > COOLDOWN_SECONDS:
                state.last_alert = now
                self._fire_alert(city, neighborhood, z_score, observed_rate, posterior_mean, lower, upper)

    def _fire_alert(self, city: str, neighborhood: str, z_score: float,
                    observed_rate: float, expected_rate: float,
                    lower: float, upper: float) -> None:
        from app.main import notify_sse_clients
        notify_sse_clients({
            "type": "anomaly",
            "city": city,
            "neighborhood": neighborhood,
            "z_score": round(z_score, 2),
            "observed_rate": round(observed_rate, 2),
            "expected_rate": round(expected_rate, 2),
            "credible_interval": [round(lower, 2), round(upper, 2)],
            "threshold": Z_THRESHOLD,
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        })

    def get_state(self, city: str, neighborhood: str) -> dict | None:
        key = (city, neighborhood)
        s = self._states.get(key)
        if s is None:
            return None
        return {"alpha": s.alpha, "beta": s.beta, "current_count": s.current_count,
                "last_update": s.last_update, "last_alert": s.last_alert}

    def reset(self) -> None:
        self._states.clear()


# Module-level singleton
_detector = BayesianAnomalyDetector()


def check_anomaly(city: str, neighborhood: str) -> None:
    _detector.on_report(city, neighborhood)


def get_state(city: str, neighborhood: str) -> dict | None:
    return _detector.get_state(city, neighborhood)


def reset_states() -> None:
    _detector.reset()
