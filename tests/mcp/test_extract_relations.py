"""
Regression tests for the MCP ``extract_relations`` tool.

Root cause of the bug
----------------------
The deployed MCP server (``semantica.mcp_server``) exposed ``extract_relations``
with a ``text``-only input schema, but the underlying
``RelationExtractor.extract_relations(text, entities)`` requires ``entities`` as a
positional argument (no default).  Calling it without ``entities`` raised
``TypeError: missing 1 required positional argument: 'entities'``.

Fix (recommendation A)
----------------------
``_tool_extract_relations`` now runs NER internally first and feeds the detected
entities into ``extract_relations``.  The MCP tool signature stays ``text``-only.
NER failures / empty results degrade gracefully to ``[]`` instead of crashing.

Run
---
    pytest tests/mcp/test_extract_relations.py -v

(Requires the full ``semantica`` environment — e.g. the MCP Docker image.)
"""

import json

import pytest

from semantica.mcp_server import TOOLS, _tool_extract_relations


# ── fixtures ────────────────────────────────────────────────────────────────
EN_TEXT = (
    "Zhang Wei proposed migrating settlement-service to PostgreSQL 16, "
    "approved by Wang Fang."
)
ZH_TEXT = "张伟提议将结算系统迁移至 PostgreSQL 16，王芳批准了该方案。"
EMPTY_TEXT = ""


def _call(text):
    """Invoke the tool and parse the JSON payload it returns."""
    raw = _tool_extract_relations({"text": text})
    return raw


# ── schema contract (recommendation A: signature stays text-only) ────────────
def test_schema_is_text_only():
    tool = next(t for t in TOOLS if t["name"] == "extract_relations")
    schema = tool["inputSchema"]
    assert schema["required"] == ["text"], "extract_relations must require only 'text'"
    assert "entities" not in schema.get("properties", {}), \
        "entities must NOT be exposed in the MCP schema"


# ── acceptance criterion #1: English → ≥1 triplet, no exception ──────────────
def test_english_returns_triplets():
    result = _call(EN_TEXT)
    assert "error" not in result, f"unexpected error: {result.get('error')}"
    triplets = result.get("triplets", [])
    assert len(triplets) >= 1, f"expected >=1 triplet, got {triplets}"
    # sanity: triplet shape is (subject, predicate, object)
    trip = triplets[0]
    assert {trip["subject"], trip["predicate"], trip["object"]} != {None}


# ── acceptance criterion #2: Chinese (weak NER recall) must not crash ────────
def test_chinese_does_not_crash():
    result = _call(ZH_TEXT)
    # Either succeeds with empty lists, or returns a graceful error dict —
    # it must never raise.
    assert isinstance(result, dict)


# ── acceptance criterion #2: empty text must not raise ──────────────────────
def test_empty_text_does_not_crash():
    result = _call(EMPTY_TEXT)
    assert isinstance(result, dict)
    assert "error" in result, "empty text should return a graceful error dict"


# ── entities must actually reach the underlying extractor (no TypeError) ─────
def test_no_missing_entities_typeerror():
    # The whole point of the fix: _tool_extract_relations must not bubble up a
    # "missing 1 required positional argument: 'entities'" TypeError.
    try:
        result = _call(EN_TEXT)
    except TypeError as exc:
        pytest.fail(f"extract_relations still raised TypeError: {exc}")
    assert isinstance(result, dict)
