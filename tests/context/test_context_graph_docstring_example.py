#!/usr/bin/env python3
"""Regression tests for the ContextGraph module docstring example.

The "Example Usage" block in ``semantica/context/context_graph.py`` previously
called ``add_node``/``add_edge`` with keyword arguments those methods do not
accept (``type=`` and ``properties=``), so the documented example raised
``TypeError`` -- and the near-miss variants silently nested the properties dict
instead of failing.

These tests keep the documented example executable and pin the two behaviours
that made the original mistake easy to miss.
"""

import doctest
import re
from typing import Dict, List

import pytest

import semantica.context.context_graph as context_graph_module
from semantica.context.context_graph import ContextGraph

# The example block runs to the next top-level section header (a line starting
# in column 0, e.g. "Production Use Cases:") or the end of the docstring.
# Terminating on the next header rather than on a blank line keeps the capture
# intact when the example gains blank lines or extra paragraphs.
_EXAMPLE_BLOCK_RE = re.compile(r"^Example Usage:\n(.*?)(?=^\S|\Z)", re.DOTALL | re.MULTILINE)

# ``type=`` as its own keyword, but not the legitimate ``node_type=``/``edge_type=``.
_BARE_TYPE_KWARG_RE = re.compile(r"(?<![\w])type\s*=")


def _example_block() -> str:
    """Return the 'Example Usage' block from the module docstring."""
    doc = context_graph_module.__doc__ or ""
    match = _EXAMPLE_BLOCK_RE.search(doc)
    assert match, "module docstring no longer contains an 'Example Usage:' block"
    block = match.group(1).strip()
    assert block, "the 'Example Usage:' block in the module docstring is empty"
    return block


def _example_statements() -> List[str]:
    """Return the documented ``>>>`` statements, continuation lines included."""
    statements = [example.source for example in doctest.DocTestParser().get_examples(_example_block())]
    assert statements, "the 'Example Usage:' block no longer contains any '>>>' statements"
    return statements


def _statements_calling(method: str) -> List[str]:
    """Return the documented statements that call ``graph.<method>(``."""
    return [stmt for stmt in _example_statements() if "graph.{}(".format(method) in stmt]


def _run_example() -> Dict[str, object]:
    """Execute the documented example verbatim and return its namespace."""
    source = "".join(_example_statements())
    namespace: Dict[str, object] = {}
    exec(compile(source, "<context_graph module docstring>", "exec"), namespace)
    return namespace


class TestDocstringExampleIsRunnable:
    """The documented example must execute exactly as written."""

    def test_documented_calls_execute(self):
        # Run the docstring text itself so this test cannot drift from the docs.
        ns = _run_example()
        graph = ns["graph"]

        assert "Python" in graph.nodes
        assert "Programming" in graph.nodes
        assert graph.nodes["Python"].node_type == "language"
        assert graph.nodes["Programming"].node_type == "concept"

        neighbors = graph.get_neighbors("Python", hops=1)
        assert any(n["id"] == "Programming" for n in neighbors)

        # record_decision must return a non-empty string ID.
        assert isinstance(ns["decision_id"], str) and ns["decision_id"]
        # find_precedents must be called with that ID and return a list.
        assert isinstance(ns["precedents"], list)

    def test_node_properties_are_stored_flat(self):
        """``popularity`` must land as a top-level property, not nested.

        Passing the previously documented ``properties={...}`` does not raise --
        it stores a dict *inside* the properties dict, which is why the original
        docs bug could reach a user's graph unnoticed.
        """
        graph = ContextGraph(advanced_analytics=False)
        graph.add_node("Python", "language", popularity="high")

        assert graph.nodes["Python"].properties == {"popularity": "high"}
        assert graph.find_node("Python")["metadata"]["popularity"] == "high"
        assert "properties" not in graph.nodes["Python"].properties

    def test_edge_type_is_positional_not_a_property(self):
        """``related_to`` must be the edge type, not a stray metadata key."""
        graph = ContextGraph(advanced_analytics=False)
        graph.add_node("Python", "language")
        graph.add_node("Programming", "concept")
        graph.add_edge("Python", "Programming", "related_to")

        edge = graph.edges[0]
        assert edge.edge_type == "related_to"
        assert "type" not in edge.metadata


class TestDocstringExampleDoesNotRegress:
    """Guard the docstring text itself, not just equivalent code."""

    def test_add_node_example_supplies_node_type_positionally(self):
        calls = _statements_calling("add_node")
        assert calls, "the 'Example Usage:' block no longer calls graph.add_node()"
        for call in calls:
            assert not _BARE_TYPE_KWARG_RE.search(call), (
                f"add_node example passes type= as a keyword: {call!r}. "
                "node_type is positional-required; type= falls through to "
                "**properties and the call raises TypeError."
            )
            assert "properties=" not in call, (
                f"add_node example passes properties=: {call!r}. "
                "add_node has no properties parameter; extra properties are "
                "passed as **kwargs."
            )

    def test_add_edge_example_supplies_edge_type_positionally(self):
        calls = _statements_calling("add_edge")
        assert calls, "the 'Example Usage:' block no longer calls graph.add_edge()"
        for call in calls:
            assert not _BARE_TYPE_KWARG_RE.search(call), (
                f"add_edge example passes type= as a keyword: {call!r}. "
                "The parameter is edge_type; type= is silently absorbed into "
                "**properties and pollutes edge metadata."
            )

    def test_broken_form_still_raises(self):
        """Pin the signature contract the example has to respect."""
        graph = ContextGraph(advanced_analytics=False)
        with pytest.raises(TypeError, match="node_type"):
            graph.add_node("Python", type="language", properties={"popularity": "high"})
