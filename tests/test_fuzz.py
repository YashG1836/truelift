"""Fuzz the service from its own OpenAPI contract (Schemathesis): whatever a caller sends, the
service answers with a documented status and a body that matches the documented schema, and never
with a server error (audit T-10, TL-012).

Slow (a minute or two): run with `python tasks.py test --all` or `pytest -m slow`.
"""

from __future__ import annotations

import pytest
import schemathesis
from hypothesis import HealthCheck, settings
from schemathesis.checks import (
    content_type_conformance,
    not_a_server_error,
    response_schema_conformance,
    status_code_conformance,
)

CHECKS = [not_a_server_error, status_code_conformance, content_type_conformance, response_schema_conformance]


@pytest.fixture
def api_schema(client):
    """The live contract of the app under test (the small model from conftest)."""
    from truelift.api import app

    return schemathesis.openapi.from_asgi("/openapi.json", app)


schema = schemathesis.pytest.from_fixture("api_schema")


@pytest.mark.slow
@schema.parametrize()
@settings(max_examples=30, deadline=None, suppress_health_check=list(HealthCheck))
def test_contract_holds_for_any_input(case):
    case.call_and_validate(checks=CHECKS)
