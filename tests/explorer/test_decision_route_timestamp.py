"""Regression tests for the /api/decisions 422 bug.

``ContextGraph.record_decision()`` stores ``timestamp`` as a POSIX float
(``datetime.now().timestamp()``).  ``DecisionResponse.timestamp`` is typed
``Optional[str]``.  Without the ``_normalize_timestamp`` field-validator on
``DecisionResponse`` the raw float fails Pydantic validation and every decision
endpoint returns 422.

The validator lives on ``DecisionResponse`` in ``semantica/explorer/schemas.py``
and converts float/int epochs to ISO-8601 strings via
``datetime.fromtimestamp(value, tz=timezone.utc).isoformat()``.

``_node_to_decision()`` must pass the raw stored value through unchanged so the
validator can do its job.  A route-level ``str()`` cast would pre-empt the
validator and produce raw numeric strings instead of ISO-8601, breaking the API
contract and all callers that call ``datetime.fromisoformat()`` on the result.

Each test below is written so that it *fails* when the route-level ``str()``
cast is present (i.e. it would have caught the regression introduced by the
incorrect fix).
"""

import math
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from semantica.context.context_graph import ContextGraph
from semantica.explorer.app import create_app
from semantica.explorer.routes.decisions import _node_to_decision
from semantica.explorer.schemas import DecisionResponse
from semantica.explorer.session import GraphSession


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _decision_node(timestamp):
    """Minimal node dict as returned by the graph session layer."""
    return {
        "id": "d-test",
        "type": "decision",
        "properties": {
            "category": "loan_underwriting",
            "scenario": "A-7291 review",
            "reasoning": "DTI within policy",
            "outcome": "approved",
            "confidence": 0.94,
            "timestamp": timestamp,
        },
    }


def _recorded_client():
    """TestClient backed by a graph built with real record_decision() calls.

    This is the path that was broken in production: record_decision() stores
    timestamp as a float epoch, which must come out the other side as an
    ISO-8601 string, not a raw numeric string.
    """
    graph = ContextGraph(advanced_analytics=False)
    graph.record_decision(
        category="credit_application",
        scenario="Personal loan, $85k income, 31% DTI",
        reasoning="Income meets threshold; employment stable",
        outcome="proceed_to_underwriting",
        confidence=0.88,
        entities=["applicant_A7291"],
    )
    return TestClient(create_app(session=GraphSession(graph)))


# ---------------------------------------------------------------------------
# Unit tests: _node_to_decision() → DecisionResponse
#
# Each assertion must fail when the route contains the incorrect str() cast:
#   timestamp=None if ... is None else str(properties.get("timestamp"))
# because that cast turns floats into numeric strings such as "1786513069.69"
# rather than ISO-8601 strings such as "2026-08-12T05:37:49+00:00".
# ---------------------------------------------------------------------------

def test_float_timestamp_becomes_iso8601():
    """A POSIX-float epoch must be normalised to an ISO-8601 string.

    Fails with the str() cast because str(1786513069.694965) ==
    '1786513069.694965', which is not a valid isoformat string.
    """
    decision = _node_to_decision(_decision_node(timestamp=1786513069.694965))

    assert isinstance(decision.timestamp, str)
    # Must parse as a valid ISO-8601 datetime — this is the key assertion that
    # the incorrect str() cast breaks.
    parsed = datetime.fromisoformat(decision.timestamp)
    # Round-trip: parsed timestamp must be within 1 s of the original epoch.
    assert abs(parsed.timestamp() - 1786513069.694965) < 1.0


def test_int_timestamp_becomes_iso8601():
    """An integer epoch (no sub-second component) must also become ISO-8601.

    Fails with the str() cast because str(1786513069) == '1786513069'.
    """
    decision = _node_to_decision(_decision_node(timestamp=1786513069))

    assert isinstance(decision.timestamp, str)
    parsed = datetime.fromisoformat(decision.timestamp)
    assert abs(parsed.timestamp() - 1786513069) < 1.0


def test_none_timestamp_stays_none():
    """A stored None must remain None, not become the string 'None'."""
    decision = _node_to_decision(_decision_node(timestamp=None))

    assert decision.timestamp is None


def test_missing_timestamp_key_stays_none():
    """A node without a timestamp key at all must not raise and must be None."""
    node = {
        "id": "d-no-ts",
        "type": "decision",
        "properties": {"category": "x", "outcome": "y"},
    }

    decision = _node_to_decision(node)

    assert decision.timestamp is None


def test_iso_string_passes_through_unchanged():
    """An already-ISO-8601 string must be returned verbatim."""
    iso = "2026-08-12T10:04:20+00:00"
    decision = _node_to_decision(_decision_node(timestamp=iso))

    assert decision.timestamp == iso


def test_nan_timestamp_raises_validation_error():
    """NaN must be rejected by the validator, not silently accepted.

    With the str() cast, str(nan) == 'nan' bypasses the validator's finiteness
    check and is silently accepted — this test would pass the incorrect version
    of the code if it expected 'nan', but it correctly expects a ValidationError.
    """
    with pytest.raises(ValidationError):
        _node_to_decision(_decision_node(timestamp=float("nan")))


def test_inf_timestamp_raises_validation_error():
    """Positive infinity must be rejected, not silently accepted as 'inf'."""
    with pytest.raises(ValidationError):
        _node_to_decision(_decision_node(timestamp=float("inf")))


def test_negative_inf_timestamp_raises_validation_error():
    """Negative infinity must be rejected, not silently accepted as '-inf'."""
    with pytest.raises(ValidationError):
        _node_to_decision(_decision_node(timestamp=float("-inf")))


def test_out_of_range_epoch_raises_validation_error():
    """A millisecond epoch accidentally passed as seconds must be rejected.

    With the str() cast, str(1723600000000) is silently accepted as a string.
    The validator correctly raises ValidationError for out-of-range epochs.
    """
    with pytest.raises(ValidationError):
        _node_to_decision(_decision_node(timestamp=1723600000000))


# ---------------------------------------------------------------------------
# Integration tests: full HTTP path through TestClient
#
# These exercise the complete production path:
#   record_decision() → float stored in graph → HTTP GET → JSON response
#
# They are the definitive check: if the route emits numeric strings instead of
# ISO-8601 the fromisoformat() assertion below fails immediately.
# ---------------------------------------------------------------------------

def test_list_decisions_float_timestamp_serialised_as_iso8601():
    """GET /api/decisions must return ISO-8601 timestamps for all decisions.

    This is the exact production failure path.  record_decision() stores
    timestamp as a float; the endpoint must return an ISO-8601 string, not a
    raw numeric string like '1786513069.69'.
    """
    with _recorded_client() as client:
        response = client.get("/api/decisions")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) >= 1

    for item in payload:
        ts = item["timestamp"]
        assert isinstance(ts, str), f"timestamp must be str, got {type(ts)}"
        # This is the line that fails when the str() cast is present:
        datetime.fromisoformat(ts)


def test_get_decision_float_timestamp_serialised_as_iso8601():
    """GET /api/decisions/{id} must return an ISO-8601 timestamp."""
    with _recorded_client() as client:
        decision_id = client.get("/api/decisions").json()[0]["decision_id"]
        response = client.get(f"/api/decisions/{decision_id}")

    assert response.status_code == 200
    ts = response.json()["timestamp"]
    assert isinstance(ts, str)
    datetime.fromisoformat(ts)


def test_get_precedents_float_timestamp_serialised_as_iso8601():
    """GET /api/decisions/{id}/precedents must return ISO-8601 timestamps."""
    graph = ContextGraph(advanced_analytics=False)
    for i in range(3):
        graph.record_decision(
            category="risk",
            scenario=f"loan assessment scenario {i}",
            reasoning="standard criteria",
            outcome="approved",
            confidence=0.9,
        )

    with TestClient(create_app(session=GraphSession(graph))) as client:
        decision_id = client.get("/api/decisions").json()[0]["decision_id"]
        response = client.get(f"/api/decisions/{decision_id}/precedents")

    assert response.status_code == 200
    for item in response.json():
        ts = item["timestamp"]
        assert isinstance(ts, str)
        datetime.fromisoformat(ts)
