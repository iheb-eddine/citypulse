"""Tests for Bayesian Anomaly Detection (app/anomaly.py)."""

import time
from unittest.mock import patch

import pytest

from app.anomaly import (
    BayesianAnomalyDetector, NeighborhoodState, check_anomaly, get_state, reset_states,
    ALPHA_FLOOR, BETA_FLOOR, MIN_OBSERVATIONS, Z_THRESHOLD, COOLDOWN_SECONDS, MIN_WINDOW_HOURS,
)


@pytest.fixture(autouse=True)
def clean_state():
    """Reset module-level detector state before each test."""
    reset_states()
    yield
    reset_states()


class TestNeighborhoodState:
    def test_defaults(self):
        s = NeighborhoodState()
        assert s.alpha == 1.0
        assert s.beta == 1.0
        assert s.current_count == 0
        assert s.last_alert == 0.0


class TestPosteriorUpdate:
    def test_accumulates_count_below_min_window(self):
        """Reports within MIN_WINDOW accumulate without triggering evaluation."""
        d = BayesianAnomalyDetector()
        d.on_report("stuttgart", "Mitte")
        state = d._states[("stuttgart", "Mitte")]
        assert state.current_count == 1
        assert state.alpha == 1.0  # No update yet

    def test_posterior_update_after_window(self):
        """After MIN_WINDOW elapsed, posterior is updated."""
        d = BayesianAnomalyDetector()
        state = d._get_or_create_state("stuttgart", "Mitte")
        # Simulate time in the past so elapsed > MIN_WINDOW
        state.last_update = time.time() - 3600  # 1 hour ago
        state.current_count = 0

        d.on_report("stuttgart", "Mitte")
        # Now current_count=1, elapsed ~1h > MIN_WINDOW → evaluation triggers
        # After update: alpha = decayed_alpha + 1, beta = decayed_beta + ~1h
        assert state.current_count == 0  # Reset after evaluation
        assert state.alpha > 1.0  # Was 1.0, decayed slightly, then +1
        assert state.beta > 1.0  # Was 1.0, decayed slightly, then +~1h


class TestZScore:
    def test_z_score_computed_before_update(self):
        """Z-score uses pre-update alpha/beta, not post-update."""
        d = BayesianAnomalyDetector()
        state = d._get_or_create_state("stuttgart", "Mitte")
        state.last_update = time.time() - 3600
        state.alpha = 10.0
        state.beta = 10.0  # mean=1.0, std=sqrt(10)/10≈0.316

        # Inject many reports to create high observed_rate
        state.current_count = 49  # Will become 50 after on_report
        # observed_rate = 50/1h = 50, z = (50 - 1.0) / 0.316 ≈ 155

        alerts_fired = []
        with patch.object(d, '_fire_alert', side_effect=lambda *a: alerts_fired.append(a)):
            d.on_report("stuttgart", "Mitte")

        # Alert should fire (z >> threshold, alpha post-update = ~10*decay + 50 > MIN_OBS)
        assert len(alerts_fired) == 1
        z_score_fired = alerts_fired[0][2]
        # z should be based on pre-update mean=1.0, not post-update mean
        assert z_score_fired > 100  # Very high because 50 >> 1.0


class TestExponentialDecay:
    def test_decay_reduces_alpha_beta(self):
        d = BayesianAnomalyDetector()
        state = d._get_or_create_state("stuttgart", "Mitte")
        state.alpha = 10.0
        state.beta = 10.0
        state.last_update = time.time() - 7200  # 2 hours ago

        d.on_report("stuttgart", "Mitte")
        # After decay: alpha = 10 * exp(-2*0.01) ≈ 9.80 + 1 = 10.80
        # beta = 10 * exp(-2*0.01) ≈ 9.80 + 2h = 11.80
        assert state.alpha < 11.0  # decayed_alpha(~9.8) + 1 = ~10.8
        assert state.beta > 11.0   # decayed_beta(~9.8) + 2h = ~11.8

    def test_decay_floor_enforced(self):
        d = BayesianAnomalyDetector()
        state = d._get_or_create_state("stuttgart", "Mitte")
        state.alpha = 0.01  # Very small
        state.beta = 0.01
        state.last_update = time.time() - 36000  # 10 hours ago

        d.on_report("stuttgart", "Mitte")
        # After decay, floors should apply: alpha >= ALPHA_FLOOR, beta >= BETA_FLOOR
        # Post-update: alpha = max(0.5, tiny) + 1 = 1.5, beta = max(0.5, tiny) + 10h
        assert state.alpha >= ALPHA_FLOOR
        assert state.beta >= BETA_FLOOR


class TestAnomalyAlert:
    def test_alert_fires_on_spike(self):
        """High observed rate triggers SSE alert."""
        d = BayesianAnomalyDetector()
        state = d._get_or_create_state("stuttgart", "Mitte")
        state.alpha = 10.0
        state.beta = 10.0
        state.last_update = time.time() - 3600

        # 50 reports in 1 hour when expected is ~1/hour → huge z-score
        state.current_count = 49

        alerts = []
        with patch("app.main.notify_sse_clients", side_effect=lambda e: alerts.append(e)):
            d.on_report("stuttgart", "Mitte")

        assert len(alerts) == 1
        assert alerts[0]["type"] == "anomaly"
        assert alerts[0]["city"] == "stuttgart"
        assert alerts[0]["neighborhood"] == "Mitte"
        assert alerts[0]["z_score"] > Z_THRESHOLD

    def test_no_alert_below_threshold(self):
        """Normal rate does not trigger alert."""
        d = BayesianAnomalyDetector()
        state = d._get_or_create_state("stuttgart", "Mitte")
        state.alpha = 10.0
        state.beta = 10.0  # mean=1.0
        state.last_update = time.time() - 3600

        # 1 report in 1 hour → rate=1.0, z≈0
        state.current_count = 0

        alerts = []
        with patch("app.main.notify_sse_clients", side_effect=lambda e: alerts.append(e)):
            d.on_report("stuttgart", "Mitte")

        assert len(alerts) == 0

    def test_min_observations_guard(self):
        """No alert when post-update alpha < MIN_OBSERVATIONS."""
        d = BayesianAnomalyDetector()
        state = d._get_or_create_state("stuttgart", "Mitte")
        state.alpha = 1.0
        state.beta = 1.0  # mean=1.0
        state.last_update = time.time() - 3600

        # 3 reports → post-update alpha ≈ 1*decay + 3 ≈ 4 < MIN_OBSERVATIONS(5)
        state.current_count = 2

        alerts = []
        with patch("app.main.notify_sse_clients", side_effect=lambda e: alerts.append(e)):
            d.on_report("stuttgart", "Mitte")

        assert len(alerts) == 0


class TestCooldown:
    def test_cooldown_suppresses_second_alert(self):
        """Second spike within cooldown does not fire alert."""
        d = BayesianAnomalyDetector()
        state = d._get_or_create_state("stuttgart", "Mitte")
        state.alpha = 10.0
        state.beta = 10.0
        state.last_update = time.time() - 3600
        state.current_count = 49

        alerts = []
        with patch("app.main.notify_sse_clients", side_effect=lambda e: alerts.append(e)):
            d.on_report("stuttgart", "Mitte")  # First alert fires
            assert len(alerts) == 1

            # Second spike immediately after
            state.last_update = time.time() - 3600
            state.current_count = 49
            d.on_report("stuttgart", "Mitte")  # Cooldown suppresses
            assert len(alerts) == 1  # Still 1

    def test_alert_fires_after_cooldown_expires(self):
        """Alert fires again after cooldown period."""
        d = BayesianAnomalyDetector()
        state = d._get_or_create_state("stuttgart", "Mitte")
        state.alpha = 10.0
        state.beta = 10.0
        state.last_update = time.time() - 3600
        state.current_count = 49

        alerts = []
        with patch("app.main.notify_sse_clients", side_effect=lambda e: alerts.append(e)):
            d.on_report("stuttgart", "Mitte")
            assert len(alerts) == 1

            # Simulate cooldown expired
            state.last_alert = time.time() - COOLDOWN_SECONDS - 1
            state.last_update = time.time() - 3600
            state.current_count = 49
            d.on_report("stuttgart", "Mitte")
            assert len(alerts) == 2


class TestPublicAPI:
    def test_check_anomaly_no_crash(self):
        """check_anomaly works for any neighborhood without crashing."""
        check_anomaly("stuttgart", "Unknown")
        state = get_state("stuttgart", "Unknown")
        assert state is not None
        assert state["current_count"] == 1

    def test_get_state_returns_none_for_unknown(self):
        assert get_state("nonexistent", "nowhere") is None

    def test_reset_states_clears_all(self):
        check_anomaly("stuttgart", "Mitte")
        assert get_state("stuttgart", "Mitte") is not None
        reset_states()
        assert get_state("stuttgart", "Mitte") is None
