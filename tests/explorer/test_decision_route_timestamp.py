"""Unit tests for the explorer decision route adapter.

Regression coverage for the ``/api/decisions`` 422 bug: a decision node
whose ``timestamp`` is stored as a POSIX float (the format
``ContextGraph.record_decision`` writes) must not break Pydantic
validation of ``DecisionResponse`` (typed ``Optional[str]``).
"""

import math

from semantica.explorer.routes.decisions import _node_to_decision
from semantica.explorer.schemas import DecisionResponse


def _decision_node(timestamp):
    """Build a minimal decision node dict shaped like ContextGraph.to_dict()."""
    return {
        "id": "d-1",
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


def test_timestamp_float_is_coerced_to_str():
    """A POSIX-float timestamp (what record_decision stores) must validate.

    Before the fix this raised a ValidationError (422 on the endpoint).
    """
    node = _decision_node(timestamp=1786513069.694965)

    decision = _node_to_decision(node)

    assert isinstance(decision, DecisionResponse)
    assert decision.timestamp == "1786513069.694965"
    # round-trips through Pydantic strict str validation
    assert decision.confidence == 0.94
    assert decision.outcome == "approved"


def test_timestamp_int_is_coerced_to_str():
    """Integer timestamps (some stores serialize without sub-second precision)
    are handled by the same coercion path."""
    decision = _node_to_decision(_decision_node(timestamp=1786513069))

    assert decision.timestamp == "1786513069"


def test_timestamp_none_is_preserved():
    """A missing timestamp must stay None, not become the string 'None'."""
    decision = _node_to_decision(_decision_node(timestamp=None))

    assert decision.timestamp is None


def test_timestamp_str_passes_through():
    """An already-string timestamp is left intact."""
    decision = _node_to_decision(_decision_node(timestamp="2026-08-12T10:04:20"))

    assert decision.timestamp == "2026-08-12T10:04:20"


def test_timestamp_missing_key_defaults_to_none():
    """A decision node without a timestamp key at all should not raise."""
    node = {
        "id": "d-2",
        "type": "decision",
        "properties": {"category": "x", "outcome": "y"},
    }

    decision = _node_to_decision(node)

    assert decision.timestamp is None


def test_float_timestamp_not_nan_or_inf():
    """Sanity guard: degenerate float values still coerce to a finite string
    rather than crashing validation."""
    for value in (float("nan"), float("inf")):
        node = _decision_node(timestamp=value)
        decision = _node_to_decision(node)
        assert isinstance(decision.timestamp, str)
        if math.isnan(value):
            assert "nan" in decision.timestamp.lower()
        else:
            assert "inf" in decision.timestamp.lower()
