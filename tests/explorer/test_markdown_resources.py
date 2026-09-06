from datetime import datetime

import pytest

from semantica.context.agent_memory import AgentMemory
from semantica.context.context_graph import ContextGraph
from semantica.explorer.markdown_resources import (
    MarkdownResourceKind,
    MarkdownResourceNotFound,
    MarkdownResourceRef,
    MarkdownResourceRegistry,
    MarkdownRevisionConflict,
    MarkdownSaveFailed,
    document_revision,
)


def _resources():
    graph = ContextGraph(advanced_analytics=False)
    graph.add_node("node-1", "Note", "Original node")
    graph.add_node("node-2", "Note", "Second node")
    memory = AgentMemory()
    memory.store(
        "Original memory",
        memory_id="mem-1",
        timestamp=datetime.fromisoformat("2026-07-22T09:00:00+00:00"),
        metadata={
            "type": "note",
            "updated_at": "2026-07-22T10:00:00+00:00",
        },
    )
    return graph, memory, MarkdownResourceRegistry(graph, memory)


def test_registry_routes_context_nodes_and_returns_canonical_revision():
    graph, _, resources = _resources()
    ref = MarkdownResourceRef(MarkdownResourceKind.CONTEXT_NODE, "node-1")

    document = resources.read(ref)

    assert document.body == "Original node"
    assert document.revision == document_revision(document.source)
    edited = document.source.replace("Original node", "Updated node")
    result = resources.apply(ref, edited, document.revision)
    assert result.changed is True
    assert result.body == "Updated node"
    assert graph.nodes["node-1"].content == "Updated node"


def test_registry_routes_agent_memory_without_touching_context_graph():
    graph, memory, resources = _resources()
    ref = MarkdownResourceRef(MarkdownResourceKind.AGENT_MEMORY, "mem-1")
    before_nodes = dict(graph.nodes)
    document = resources.read(ref)

    result = resources.apply(
        ref,
        document.source.replace("Original memory", "Updated memory"),
        document.revision,
    )

    assert result.body == "Updated memory"
    assert memory.get("mem-1")["content"] == "Updated memory"
    assert graph.nodes == before_nodes


def test_registry_rejects_stale_revision_and_preserves_current_state():
    graph, _, resources = _resources()
    ref = MarkdownResourceRef(MarkdownResourceKind.CONTEXT_NODE, "node-1")
    first = resources.read(ref)
    resources.apply(
        ref,
        first.source.replace("Original node", "First update"),
        first.revision,
    )

    with pytest.raises(MarkdownRevisionConflict) as error:
        resources.apply(
            ref,
            first.source.replace("Original node", "Stale update"),
            first.revision,
        )

    assert error.value.current_revision == resources.read(ref).revision
    assert graph.nodes["node-1"].content == "First update"


def test_registry_missing_adapter_and_resources_are_structured():
    graph, _, _ = _resources()
    resources = MarkdownResourceRegistry(graph)

    with pytest.raises(MarkdownResourceNotFound, match="not available"):
        resources.read(MarkdownResourceRef(MarkdownResourceKind.AGENT_MEMORY, "mem-1"))
    with pytest.raises(MarkdownResourceNotFound, match="missing"):
        resources.read(
            MarkdownResourceRef(MarkdownResourceKind.CONTEXT_NODE, "missing")
        )


def test_registry_does_not_expose_adapter_failure_details(monkeypatch):
    graph, _, resources = _resources()
    ref = MarkdownResourceRef(MarkdownResourceKind.CONTEXT_NODE, "node-1")
    document = resources.read(ref)

    def fail(_resource_id, _source):
        raise RuntimeError("private backend failure")

    monkeypatch.setattr(graph, "apply_node_markdown", fail)
    with pytest.raises(MarkdownSaveFailed) as error:
        resources.apply(ref, document.source + "changed", document.revision)

    assert error.value.message == (
        "The edit could not be applied. The existing item was not changed."
    )
    assert "private backend failure" not in error.value.message
