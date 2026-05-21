"""CityPulse Observability — metrics, structured logging, health check."""

import json
import logging
import os
import time
import uuid
from collections import deque
from typing import Optional

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy import text
from starlette.middleware.base import BaseHTTPMiddleware

_START_TIME = time.time()
_ERROR_RATE_THRESHOLD = float(os.environ.get("ERROR_RATE_ALERT_THRESHOLD", "0.1"))
_METRICS_API_KEY = os.environ.get("METRICS_API_KEY", "")
_ALERT_COOLDOWN = 60
_WINDOW_SECONDS = 300
_MAX_SAMPLES = 10000

logger = logging.getLogger("citypulse")


class _JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        obj = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "message": record.getMessage(),
        }
        for key in ("request_id", "method", "path", "status", "duration_ms", "alert", "rate", "threshold", "window_seconds"):
            val = getattr(record, key, None)
            if val is not None:
                obj[key] = val
        return json.dumps(obj)


def setup_logging() -> None:
    """Configure structured JSON logging on stdout."""
    handler = logging.StreamHandler()
    handler.setFormatter(_JSONFormatter(datefmt="%Y-%m-%dT%H:%M:%S"))
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    # Suppress uvicorn access log to avoid duplicate lines
    logging.getLogger("uvicorn.access").propagate = False
    logging.getLogger("uvicorn.access").handlers.clear()


class MetricsStore:
    """In-memory metrics: per-endpoint latency + rolling error rate."""

    _SKIP_PATHS = {"/health", "/metrics"}

    def __init__(self) -> None:
        self.request_count = 0
        self.error_count = 0
        self._latencies: dict[str, deque] = {}
        self._error_buckets: deque = deque(maxlen=_MAX_SAMPLES)
        self._request_buckets: deque = deque(maxlen=_MAX_SAMPLES)
        self._last_alert_time = 0.0

    def record(self, path: str, status: int, duration_ms: float) -> None:
        if path in self._SKIP_PATHS:
            return
        self.request_count += 1
        if path not in self._latencies:
            self._latencies[path] = deque(maxlen=_MAX_SAMPLES)
        self._latencies[path].append(duration_ms)
        now = time.time()
        self._request_buckets.append((now, 1))
        if status >= 500:
            self.error_count += 1
            self._error_buckets.append((now, 1))

    def get_error_rate(self) -> float:
        now = time.time()
        cutoff = now - _WINDOW_SECONDS
        # Prune old entries from front of deque (oldest first)
        while self._error_buckets and self._error_buckets[0][0] < cutoff:
            self._error_buckets.popleft()
        while self._request_buckets and self._request_buckets[0][0] < cutoff:
            self._request_buckets.popleft()
        window_errors = len(self._error_buckets)
        window_requests = len(self._request_buckets)
        if window_requests == 0:
            return 0.0
        return window_errors / window_requests

    def check_alert(self) -> bool:
        """Return True if alert should fire (rate exceeded + cooldown passed)."""
        rate = self.get_error_rate()
        if rate > _ERROR_RATE_THRESHOLD:
            now = time.time()
            if now - self._last_alert_time >= _ALERT_COOLDOWN:
                self._last_alert_time = now
                logger.critical(
                    "error_rate_exceeded",
                    extra={"alert": "error_rate_exceeded", "rate": round(rate, 4), "threshold": _ERROR_RATE_THRESHOLD, "window_seconds": _WINDOW_SECONDS},
                )
                return True
        return False

    def percentile(self, samples: deque, p: float) -> float:
        if not samples:
            return 0.0
        s = sorted(samples)
        idx = int(len(s) * p / 100)
        return round(s[min(idx, len(s) - 1)], 2)

    def snapshot(self) -> dict:
        endpoints = {}
        for path, samples in self._latencies.items():
            endpoints[path] = {
                "count": len(samples),
                "p50": self.percentile(samples, 50),
                "p95": self.percentile(samples, 95),
                "p99": self.percentile(samples, 99),
            }
        return {
            "request_count": self.request_count,
            "error_count": self.error_count,
            "error_rate": round(self.get_error_rate(), 4),
            "endpoints": endpoints,
        }


metrics_store = MetricsStore()


class ObservabilityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        start = time.time()
        response = await call_next(request)
        # Post-response observability — isolated from response flow
        try:
            duration_ms = round((time.time() - start) * 1000, 2)
            status = response.status_code
            path = request.url.path
            route = request.scope.get("route")
            metrics_path = route.path if route else "__unmatched__"
            response.headers["X-Request-ID"] = request_id
            metrics_store.record(metrics_path, status, duration_ms)
            logger.info(
                f"{request.method} {path} {status}",
                extra={"request_id": request_id, "method": request.method, "path": path, "status": status, "duration_ms": duration_ms},
            )
            metrics_store.check_alert()
        except Exception:
            pass
        return response


async def health_check(request: Request) -> JSONResponse:
    """GET /health — app status, uptime, DB connectivity."""
    import asyncio
    from app.database import engine

    uptime = round(time.time() - _START_TIME, 1)
    db_status = "ok"

    def _check_db():
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))

    try:
        await asyncio.wait_for(asyncio.to_thread(_check_db), timeout=2.0)
    except asyncio.TimeoutError:
        db_status = "timeout"
    except Exception:
        db_status = "error"
    status_code = 200 if db_status == "ok" else 503
    return JSONResponse(status_code=status_code, content={
        "status": "healthy" if db_status == "ok" else "degraded",
        "uptime_seconds": uptime,
        "db": db_status,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    })


async def get_metrics(request: Request) -> Response:
    """GET /metrics — per-endpoint stats, optional API key protection."""
    if _METRICS_API_KEY:
        key = request.query_params.get("key", "") or request.headers.get("x-api-key", "")
        if key != _METRICS_API_KEY:
            return JSONResponse(status_code=403, content={"error": "Forbidden"})
    return JSONResponse(metrics_store.snapshot())
