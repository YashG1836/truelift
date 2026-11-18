"""Error tracking is off unless TRUELIFT_SENTRY_DSN is set, and never sends personal data (plan D9)."""

from __future__ import annotations

import sys
import types

from truelift.observability import init_error_tracking
from truelift.settings import load_settings


def test_off_by_default(monkeypatch):
    monkeypatch.delenv("TRUELIFT_SENTRY_DSN", raising=False)
    assert load_settings().sentry_dsn == ""
    assert init_error_tracking("") is False


def test_a_dsn_without_the_package_leaves_it_off(monkeypatch):
    monkeypatch.setitem(sys.modules, "sentry_sdk", None)  # import fails as if not installed
    assert init_error_tracking("https://key@example.invalid/1") is False


def test_errors_only_and_no_personal_data(monkeypatch):
    calls = {}
    fake = types.ModuleType("sentry_sdk")
    fake.init = lambda **kw: calls.update(kw)  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "sentry_sdk", fake)
    assert init_error_tracking("https://key@example.invalid/1") is True
    assert calls["send_default_pii"] is False
    assert calls["traces_sample_rate"] == 0.0
    assert calls["max_request_body_size"] == "never"
