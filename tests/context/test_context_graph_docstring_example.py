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

import re

import pytest

import semantica.context.context_graph as context_graph_module
from semantica.context.context_graph import ContextGraph


def _example_block() -> str:
    """Return the 'Example Usage' block from the module docstring."""
    doc = context_graph_module.__doc__ or ""
    match = re.search(r"Example Usage:\n(.*?)\n\n", doc, re.DOTALL)
    assert match, "module docstring no longer contains an 'Example Usage:' block"
    return match.group(1)


class TestDocstringExampleIsRunnable:
    """The documented example must execute exactly as written."""

    def test_documented_calls_execute(self):
        graph = ContextGraph(
            advanced_analytics=True,
            centrality_analysis=True,
            community_detection=True,
            node_embeddings=True,
        )

        # Basic graph operations, verbatim from the docstring.
        graph.add_node("Python", "language", popularity="high")
        graph.add_node("Programming", "concept")
        graph.add_edge("Python", "Programming", "related_to")

        assert "Python" in graph.nodes
        assert "Programming" in graph.nodes
        assert graph.nodes["Python"].node_type == "language"
        assert graph.nodes["Programming"].node_type == "concept"

        neighbors = graph.get_neighbors("Python", hops=1)
        assert any(n["id"] == "Programming" for n in neighbors)

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
        block = _example_block()
        for line in re.findall(r">>> graph\.add_node\(.*", block):
            assert "type=" not in line, (
                f"add_node example passes type= as a keyword: {line!r}. "
                "node_type is positional-required; type= falls through to "
                "**properties and the call raises TypeError."
            )
            assert "properties=" not in line, (
                f"add_node example passes properties=: {line!r}. "
                "add_node has no properties parameter; extra properties are "
                "passed as **kwargs."
            )

    def test_add_edge_example_supplies_edge_type_positionally(self):
        block = _example_block()
        for line in re.findall(r">>> graph\.add_edge\(.*", block):
            assert "type=" not in line, (
                f"add_edge example passes type= as a keyword: {line!r}. "
                "The parameter is edge_type; type= is silently absorbed into "
                "**properties and pollutes edge metadata."
            )

    def test_broken_form_still_raises(self):
        """Pin the signature contract the example has to respect."""
        graph = ContextGraph(advanced_analytics=False)
        with pytest.raises(TypeError, match="node_type"):
            graph.add_node("Python", type="language", properties={"popularity": "high"})
