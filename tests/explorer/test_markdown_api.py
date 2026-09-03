"""Integration tests for Explorer Markdown and memory selection routes."""

import threading
from datetime import datetime

import pytest

from semantica.context.agent_memory import AgentMemory
from semantica.context.context_graph import ContextGraph

pytest.importorskip("fastapi")

from starlette.testclient import TestClient  # noqa: E402

from semantica.explorer.app import create_app  # noqa: E402
from semantica.explorer.session import GraphSession  # noqa: E402


@pytest.fixture
def markdown_client():
    graph = ContextGraph(advanced_analytics=False)
    graph.add_node("editable-node", "Note", "Original node")
    events = []
    graph.mutation_callback = lambda *event: events.append(event)
    memory = AgentMemory()
    memory.store(
        "Original memory",
        memory_id="editable-memory",
        metadata={
            "type": "note",
            "updated_at": "2026-07-22T10:00:00+00:00",
        },
        timestamp=datetime.fromisoformat("2026-07-22T09:00:00+00:00"),
    )
    app = create_app(session=GraphSession(graph), agent_memory=memory)
    with TestClient(app) as test_client:
        yield test_client, graph, memory, events


def test_gets_context_node_and_agent_memory(markdown_client):
    client, _, _, _ = markdown_client

    info = client.get("/api/info")
    node = client.get("/api/markdown/context-node/editable-node")
    memory = client.get("/api/markdown/agent-memory/editable-memory")

    assert info.json()["capabilities"]["agent_memory"] is True
    assert node.status_code == 200
    assert node.json()["body"] == "Original node"
    assert node.json()["resource"] == {
        "kind": "context-node",
        "id": "editable-node",
    }
    assert node.json()["source"].startswith("---\n")
    assert node.json()["revision"].startswith("sha256:")
    assert node.json()["editable"] is True
    assert memory.status_code == 200
    assert memory.json()["body"] == "Original memory"


@pytest.mark.parametrize(
    ("kind", "resource_id", "original", "updated"),
    [
        ("context-node", "editable-node", "Original node", "Updated node"),
        ("agent-memory", "editable-memory", "Original memory", "Updated memory"),
    ],
)
def test_put_updates_exact_resource(
    markdown_client, kind, resource_id, original, updated
):
    client, graph, memory, _ = markdown_client
    current = client.get(f"/api/markdown/{kind}/{resource_id}").json()

    response = client.put(
        f"/api/markdown/{kind}/{resource_id}",
        json={
            "markdown": current["source"].replace(original, updated),
            "expected_revision": current["revision"],
        },
    )

    assert response.status_code == 200
    assert response.json()["changed"] is True
    assert response.json()["body"] == updated
    assert client.get(f"/api/markdown/{kind}/{resource_id}").json()["body"] == updated
    if kind == "context-node":
        assert graph.nodes[resource_id].content == updated
        assert memory.get("editable-memory")["content"] == "Original memory"
    else:
        assert memory.get(resource_id)["content"] == updated
        assert graph.nodes["editable-node"].content == "Original node"


def test_validation_and_identity_errors_preserve_resource(markdown_client):
    client, graph, _, events = markdown_client
    current = client.get("/api/markdown/context-node/editable-node").json()

    invalid = client.put(
        "/api/markdown/context-node/editable-node",
        json={
            "markdown": "---\nid: [\n---\n\nBroken",
            "expected_revision": current["revision"],
        },
    )
    mismatch = client.put(
        "/api/markdown/context-node/editable-node",
        json={
            "markdown": current["source"].replace(
                "id: editable-node", "id: different-node"
            ),
            "expected_revision": current["revision"],
        },
    )

    assert invalid.status_code == 422
    assert invalid.json()["detail"]["code"] == "invalid_markdown_frontmatter"
    assert "invalid YAML" in invalid.json()["detail"]["message"]
    assert mismatch.status_code == 422
    assert mismatch.json()["detail"] == {
        "code": "resource_identity_mismatch",
        "message": (
            "Frontmatter id 'different-node' does not match resource id "
            "'editable-node'."
        ),
        "field": "id",
    }
    assert graph.nodes["editable-node"].content == "Original node"
    assert events == []


def test_stale_revision_returns_conflict(markdown_client):
    client, _, _, _ = markdown_client
    current = client.get("/api/markdown/context-node/editable-node").json()
    first = client.put(
        "/api/markdown/context-node/editable-node",
        json={
            "markdown": current["source"].replace("Original node", "First update"),
            "expected_revision": current["revision"],
        },
    )
    stale = client.put(
        "/api/markdown/context-node/editable-node",
        json={
            "markdown": current["source"].replace("Original node", "Stale update"),
            "expected_revision": current["revision"],
        },
    )

    assert first.status_code == 200
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "markdown_revision_conflict"
    assert stale.json()["detail"]["current_revision"] == first.json()["revision"]


def test_missing_and_failed_apply_are_structured(markdown_client, monkeypatch):
    client, graph, _, _ = markdown_client
    missing = client.get("/api/markdown/context-node/missing")
    current = client.get("/api/markdown/context-node/editable-node").json()

    def fail(_resource_id, _document):
        raise RuntimeError("private storage failure")

    monkeypatch.setattr(graph, "apply_node_markdown", fail)
    failed = client.put(
        "/api/markdown/context-node/editable-node",
        json={
            "markdown": current["source"].replace("Original node", "Will fail"),
            "expected_revision": current["revision"],
        },
    )

    assert missing.status_code == 404
    assert missing.json()["detail"]["code"] == "markdown_resource_not_found"
    assert failed.status_code == 500
    assert failed.json()["detail"] == {
        "code": "markdown_save_failed",
        "message": "The edit could not be applied. The existing item was not changed.",
    }
    assert "private storage failure" not in failed.text


def test_lists_memories_for_selection(markdown_client):
    client, _, _, _ = markdown_client

    response = client.get("/api/memories?skip=0&limit=100")

    assert response.status_code == 200
    assert response.json() == {
        "items": [
            {
                "id": "editable-memory",
                "type": "note",
                "excerpt": "Original memory",
                "updated_at": "2026-07-22T10:00:00+00:00",
            }
        ],
        "total": 1,
        "skip": 0,
        "limit": 100,
    }


def test_memory_listing_is_atomic_with_concurrent_mutation(
    markdown_client, monkeypatch
):
    client, _, memory, _ = markdown_client
    snapshot_ready = threading.Event()
    mutation_attempted = threading.Event()
    mutation_finished = threading.Event()

    def pause_after_key_snapshot(*, offset=0, limit=100, **_filters):
        memory_ids = list(memory.memory_items.keys())[offset : offset + limit]
        snapshot_ready.set()
        assert mutation_attempted.wait(timeout=1)
        mutation_finished.wait(timeout=0.25)

        records = []
        for memory_id in memory_ids:
            # Match AgentMemory.list()'s second dictionary lookup after its
            # key snapshot; this raises if a concurrent writer is not excluded.
            memory.memory_items[memory_id]
            record = memory.get_memory(memory_id)
            if record is not None:
                records.append(record)
        return records

    monkeypatch.setattr(memory, "list", pause_after_key_snapshot)

    def delete_memory() -> None:
        assert snapshot_ready.wait(timeout=1)
        mutation_attempted.set()
        memory.delete_memory("editable-memory")
        mutation_finished.set()

    writer = threading.Thread(target=delete_memory)
    writer.start()
    try:
        response = client.get("/api/memories?skip=0&limit=100")
    finally:
        writer.join(timeout=2)

    assert not writer.is_alive()
    assert response.status_code == 200
    assert [item["id"] for item in response.json()["items"]] == ["editable-memory"]
    assert response.json()["total"] == 1


def test_default_app_does_not_expose_agent_memory():
    graph = ContextGraph(advanced_analytics=False)
    with TestClient(create_app(session=GraphSession(graph))) as client:
        info = client.get("/api/info")
        memories = client.get("/api/memories")

    assert info.json()["capabilities"]["agent_memory"] is False
    assert memories.status_code == 503
    assert memories.json()["detail"] == (
        "AgentMemory is not configured for this Explorer instance."
    )


def test_slash_and_unicode_node_id_round_trip():
    """GET and PUT work for node IDs containing '/' and Unicode characters.

    Tests that:
    - encodeURIComponent-style %2F encoding is transparent to the route
    - the returned resource.id is the original unencoded string
    - a successful PUT persists to the correct node
    - the node ID is never rewritten by the apply path
    """
    node_id = "policy/\u6771\u4eac"  # "policy/東京"
    graph = ContextGraph(advanced_analytics=False)
    graph.add_node(node_id, "Policy", "Original slash body")
    app = create_app(session=GraphSession(graph))

    with TestClient(app) as client:
        # GET via percent-encoded path (what encodeURIComponent produces)
        import urllib.parse
        encoded_id = urllib.parse.quote(node_id, safe="")
        get_response = client.get(f"/api/markdown/context-node/{encoded_id}")

        assert get_response.status_code == 200, (
            f"GET returned {get_response.status_code}: {get_response.text}"
        )
        doc = get_response.json()
        assert doc["resource"]["id"] == node_id, (
            f"resource.id should be {node_id!r}, got {doc['resource']['id']!r}"
        )
        assert doc["resource"]["kind"] == "context-node"
        assert doc["body"] == "Original slash body"
        assert doc["revision"].startswith("sha256:")

        # PUT an edit back via the same percent-encoded URL
        updated_markdown = doc["source"].replace("Original slash body", "Updated slash body")
        put_response = client.put(
            f"/api/markdown/context-node/{encoded_id}",
            json={
                "markdown": updated_markdown,
                "expected_revision": doc["revision"],
            },
        )

        assert put_response.status_code == 200, (
            f"PUT returned {put_response.status_code}: {put_response.text}"
        )
        result = put_response.json()
        assert result["changed"] is True
        assert result["body"] == "Updated slash body"
        assert result["resource"]["id"] == node_id, (
            f"PUT response resource.id should be {node_id!r}, got {result['resource']['id']!r}"
        )

        # Verify the live graph node was updated
        assert graph.nodes[node_id].content == "Updated slash body"

        # Also verify GET via literal slash URL works identically
        get_literal = client.get(f"/api/markdown/context-node/{node_id}")
        assert get_literal.status_code == 200
        assert get_literal.json()["resource"]["id"] == node_id
        assert get_literal.json()["body"] == "Updated slash body"
