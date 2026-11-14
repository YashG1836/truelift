"""Watching the service while it runs: JSON request logs, Prometheus metrics, security headers.

Metrics (served at /metrics in the Prometheus text format, audit A16 O3):
  truelift_request_seconds{route}            latency by hook
  truelift_serve_decisions_total{decision}   show, control, not_eligible, no_offer
  truelift_serve_fallback_total              decision tables built with the owner's rule; must stay 0
  truelift_holdout_share                     held-out share of eligible visits across measured weeks
  truelift_offers{status}                    demo offers by status
  truelift_model_info{version,trained_at}    which model is live
  truelift_forecast_minus_measured_ratio     (forecast - measured) / |measured| of the latest measured week
Labels never carry customer ids or restaurant names.
"""
from __future__ import annotations

import json
import logging
import sys
import time
import uuid

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram

REGISTRY = CollectorRegistry(auto_describe=True)
REQUEST_SECONDS = Histogram("truelift_request_seconds", "Request latency by route", ["route"], registry=REGISTRY,
                            buckets=(0.0005, 0.001, 0.0025, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5))
SERVE_DECISIONS = Counter("truelift_serve_decisions", "Serving decisions by outcome", ["decision"], registry=REGISTRY)
SERVE_FALLBACK = Counter("truelift_serve_fallback", "Decision tables that fell back to the owner's rule",
                         registry=REGISTRY)
HOLDOUT_SHARE = Gauge("truelift_holdout_share", "Held-out share of eligible visits across measured weeks",
                      registry=REGISTRY)
OFFERS = Gauge("truelift_offers", "Demo offers by status", ["status"], registry=REGISTRY)
MODEL_INFO = Gauge("truelift_model_info", "Model currently loaded", ["version", "trained_at"], registry=REGISTRY)
FORECAST_RATIO = Gauge("truelift_forecast_minus_measured_ratio",
                       "(forecast - measured) / |measured| for the latest measured week", registry=REGISTRY)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        base = {"ts": round(record.created, 3), "level": record.levelname.lower(), "logger": record.name,
                "msg": record.getMessage()}
        extra = getattr(record, "fields", None)
        if isinstance(extra, dict):
            base.update(extra)
        if record.exc_info:
            base["exc"] = self.formatException(record.exc_info)
        return json.dumps(base, ensure_ascii=True, default=str)


def configure_logging(json_lines: bool) -> logging.Logger:
    logger = logging.getLogger("truelift")
    if not any(getattr(h, "_truelift", False) for h in logger.handlers):
        h = logging.StreamHandler(sys.stdout)
        h.setFormatter(JsonFormatter() if json_lines else logging.Formatter("%(levelname)s %(name)s %(message)s"))
        h._truelift = True  # type: ignore[attr-defined]
        logger.addHandler(h)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return logger


REQUEST_LOG = logging.getLogger("truelift.request")

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}
# The demo page only: inline style attributes are used, scripts come from the same origin.
PAGE_CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
            "font-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'")


class ObservabilityMiddleware:
    """Pure ASGI middleware: timing, correlation id, one JSON log line, metrics, security headers."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        t0 = time.perf_counter()
        cid = uuid.uuid4().hex[:12]
        scope.setdefault("state", {})["correlation_id"] = cid
        status_holder = {"status": 500}
        path = scope.get("path", "")

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                status_holder["status"] = message["status"]
                headers = list(message.get("headers", []))
                headers.append((b"x-correlation-id", cid.encode()))
                for k, v in SECURITY_HEADERS.items():
                    headers.append((k.lower().encode(), v.encode()))
                if path == "/" or path.startswith("/static"):
                    headers.append((b"content-security-policy", PAGE_CSP.encode()))
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            dt = time.perf_counter() - t0
            route = scope.get("route")
            template = getattr(route, "path", None) or ("/static" if path.startswith("/static") else path)
            REQUEST_SECONDS.labels(route=template).observe(dt)
            st = scope.get("state", {})
            REQUEST_LOG.info("request", extra={"fields": {
                "route": template, "method": scope.get("method"), "status": status_holder["status"],
                "ms": round(dt * 1000, 2), "correlation_id": cid, "session": st.get("session"),
                "restaurant": st.get("restaurant"), "offer": st.get("offer"),
                "decision": st.get("decision"), "fallback": st.get("fallback")}})
