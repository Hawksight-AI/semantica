"""
Semantic retrieval tools — store, retrieve, update and remove documents
in a vector store, combined with knowledge-graph context (#1235).

Design notes:

• Documents are chunked with a fixed sliding window (default 1000 chars,
  200 overlap) and every chunk carries full provenance metadata:
  chunk_id, source, authority, version, project, content hash, status
  and character offsets.
• (source, version) is the upsert key.  The content hash only decides
  whether a re-store can be skipped as a no-op.
• Updates and removals on the in-memory backend rebuild the store from
  scratch (read everything, filter, clear, re-store) instead of calling
  delete_vectors.  In-memory ids are derived from ``len(self.vectors)``
  and fall back after a delete, so deleting then writing can overwrite
  live data (#1029).  Rebuilding from an empty dict starts the counter
  at zero — nothing to collide with.  The real fix for #1029 (ids that
  never get reused) belongs in its own PR.
• Retrieval results are combined with related graph nodes: for each hit
  source we look up ContextGraph nodes tagged with the same
  ``metadata.source`` and attach their 1-hop neighbours.
"""

from __future__ import annotations

import hashlib
import logging
import os
from typing import Any, Dict, List, Tuple

import numpy as np

from mcp.schemas import (
    REMOVE_DOCUMENT,
    RETRIEVE_CONTEXT,
    STORE_DOCUMENT,
    UPDATE_DOCUMENT,
)
from mcp.session import get_embedder, get_graph, get_vector_store

log = logging.getLogger("semantica.mcp.tools.retrieval")

DEFAULT_CHUNK_SIZE = 1000
DEFAULT_CHUNK_OVERLAP = 200
MAX_TOP_K = 10
FILTER_OVERFETCH = 3


def _chunk_text(text: str, chunk_size: int, chunk_overlap: int) -> List[Tuple[int, int, str]]:
    """Split text into (char_start, char_end, chunk) windows."""
    if chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be smaller than chunk_size")
    chunks: List[Tuple[int, int, str]] = []
    start = 0
    n = len(text)
    while start < n:
        end = min(start + chunk_size, n)
        chunks.append((start, end, text[start:end]))
        if end >= n:
            break
        start = end - chunk_overlap
    return chunks


def _chunk_id(source: str, version: str, index: int, text: str) -> str:
    """Stable chunk id derived from the location key and chunk content."""
    digest = hashlib.sha256(
        f"{source}|{version}|{index}|{text}".encode("utf-8")
    ).hexdigest()
    return f"chk_{digest[:16]}"


def _doc_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _find_matching_ids(store: Any, source: str, version: str) -> List[str]:
    """Return every vector id whose metadata matches (source, version)."""
    if getattr(store, "backend", "") == "inmemory":
        return [
            vid
            for vid, meta in getattr(store, "metadata", {}).items()
            if meta.get("source") == source and meta.get("version") == version
        ]
    backend_store = getattr(store, "_backend_store", None)
    if backend_store is not None and hasattr(backend_store, "filter_by_metadata"):
        # filter_by_metadata pulls whole rows (vector included) into
        # memory; 10k chunks is far above any single document's chunk
        # count while keeping the scan bounded.
        hits = backend_store.filter_by_metadata(
            {"source": source, "version": version}, limit=10_000
        )
        return [h["id"] for h in hits]
    raise NotImplementedError(
        f"Backend {type(backend_store).__name__} does not support metadata lookup; "
        "cannot locate chunks for update/remove"
    )


def _remove_ids(store: Any, remove_ids: List[str]) -> None:
    """Remove vectors by id, avoiding the #1029 in-memory id collision."""
    if getattr(store, "backend", "") == "inmemory":
        # Full rebuild: read all, filter in memory, clear, re-store once.
        # store_vectors derives ids from len(self.vectors), and the dicts
        # are empty here, so the counter restarts at zero — no reuse of
        # ids that are still referenced anywhere.
        remove = set(remove_ids)
        vectors = getattr(store, "vectors", {})
        metadata = getattr(store, "metadata", {})
        saved_vectors = dict(vectors)
        saved_metadata = dict(metadata)
        keep_vectors = []
        keep_meta = []
        for vid, vec in list(vectors.items()):
            if vid in remove:
                continue
            keep_vectors.append(vec)
            keep_meta.append(metadata.get(vid, {}))
        vectors.clear()
        metadata.clear()
        try:
            if keep_vectors:
                store.store_vectors(keep_vectors, keep_meta)
        except Exception:
            # Restore the pre-rebuild state so a failed re-store does not
            # silently drop every surviving document.
            vectors.update(saved_vectors)
            metadata.update(saved_metadata)
            store.indexer.create_index(
                list(vectors.values()), list(vectors.keys())
            )
            raise
        return
    # Persistent backends do not have the len-based id collision, so a
    # direct delete is safe there.
    store.delete_vectors(remove_ids)


def _persist(store: Any) -> None:
    """Persist the store when SEMANTICA_VECTOR_PATH is configured."""
    path = os.environ.get("SEMANTICA_VECTOR_PATH", "").strip()
    if not path:
        return
    try:
        store.save(path)
    except Exception as exc:
        log.warning("Could not persist vector store to %s: %s", path, exc)


def _node_source(meta: Any) -> str:
    """
    Extract a node's source tag from its metadata.

    ContextGraph.add_node nests the caller-supplied metadata dict one
    level down (``{'label': ..., 'metadata': {...}}``), while nodes added
    through other paths may carry ``source`` directly.  Check both.
    """
    if not isinstance(meta, dict):
        return ""
    direct = meta.get("source")
    if direct:
        return str(direct)
    nested = meta.get("metadata")
    if isinstance(nested, dict):
        return str(nested.get("source", "") or "")
    return ""


def _graph_relationships(sources: List[str], max_per_source: int = 3) -> List[Dict[str, Any]]:
    """
    Collect 1-hop graph neighbours for nodes tagged with the hit sources.

    Node lookup matches the node's source tag against the stored document
    sources.  Failures degrade to an empty list — graph context is a
    bonus, never a hard dependency of retrieval.
    """
    if not sources:
        return []
    try:
        graph = get_graph()
        nodes = list(graph.find_nodes())
    except Exception as exc:
        log.debug("Graph context unavailable: %s", exc)
        return []

    relationships: List[Dict[str, Any]] = []
    seen: set = set()
    for source in sources:
        anchor = None
        for n in nodes:
            if _node_source(n.get("metadata")) == source:
                anchor = n
                break
        if anchor is None:
            continue
        try:
            neighbors = graph.get_neighbors(anchor["id"], hops=1)
        except Exception as exc:
            log.debug("get_neighbors failed for %s: %s", anchor.get("id"), exc)
            continue
        added = 0
        for nb in neighbors:
            key = (anchor.get("id"), nb.get("id"), nb.get("relationship"))
            if key in seen:
                continue
            seen.add(key)
            relationships.append(
                {
                    "node": {
                        "id": anchor.get("id"),
                        "type": anchor.get("type"),
                        "content": str(anchor.get("content") or "")[:200],
                        "source": source,
                    },
                    "related": {
                        "id": nb.get("id"),
                        "type": nb.get("type"),
                        "content": str(nb.get("content") or "")[:200],
                    },
                    "relationship": nb.get("relationship"),
                }
            )
            added += 1
            if added >= max_per_source:
                break
    return relationships


def _upsert(args: dict, action: str) -> dict:
    """Shared implementation for store_document and update_document."""
    content = args.get("content", "")
    source = str(args.get("source", "")).strip()
    if not content or not source:
        return {"error": "content and source are required"}
    authority = str(args.get("authority", "")).strip()
    if action == "store" and not authority:
        return {"error": "authority is required"}
    version = str(args.get("version", "")).strip() or "v1"
    project = str(args.get("project", "")).strip() or None
    chunk_size = int(args.get("chunk_size", DEFAULT_CHUNK_SIZE))
    chunk_overlap = int(args.get("chunk_overlap", DEFAULT_CHUNK_OVERLAP))
    if chunk_overlap >= chunk_size:
        return {"error": "chunk_overlap must be smaller than chunk_size"}
    extra = args.get("metadata") or {}
    doc_hash = _doc_hash(content)

    try:
        store = get_vector_store()
        embedder = get_embedder()

        existing_ids = _find_matching_ids(store, source, version)
        existing_first: Dict[str, Any] = {}
        if existing_ids:
            existing_first = store.get_metadata(existing_ids[0]) or {}
            if action == "store" and existing_first.get("hash") == doc_hash:
                # Same content already stored under (source, version) —
                # skip re-embedding entirely.
                return {
                    "status": "unchanged",
                    "source": source,
                    "version": version,
                    "chunk_ids": [
                        (store.get_metadata(vid) or {}).get("chunk_id")
                        for vid in existing_ids
                    ],
                }

        chunks = _chunk_text(content, chunk_size, chunk_overlap)
        vectors = np.asarray(
            embedder.generate_embeddings([c_text for _, _, c_text in chunks])
        )
        if vectors.ndim == 1:
            vectors = vectors.reshape(1, -1)
        if vectors.shape[0] != len(chunks):
            return {
                "error": (
                    f"embedder returned {vectors.shape[0]} vectors "
                    f"for {len(chunks)} chunks"
                )
            }

        final_authority = authority or existing_first.get("authority") or "unknown"
        final_project = project or existing_first.get("project")

        if existing_ids:
            _remove_ids(store, existing_ids)

        metas = []
        chunk_ids = []
        for idx, (start, end, c_text) in enumerate(chunks):
            cid = _chunk_id(source, version, idx, c_text)
            chunk_ids.append(cid)
            meta: Dict[str, Any] = {
                "chunk_id": cid,
                "text": c_text,
                "source": source,
                "authority": final_authority,
                "version": version,
                "hash": doc_hash,
                "status": "active",
                "chunk_index": idx,
                "char_start": start,
                "char_end": end,
            }
            if final_project:
                meta["project"] = final_project
            meta.update(extra)
            metas.append(meta)

        store.store_vectors(list(vectors), metas)
        _persist(store)
        return {
            "status": "stored" if action == "store" else "updated",
            "source": source,
            "version": version,
            "chunk_ids": chunk_ids,
            "chunk_count": len(chunk_ids),
            "hash": doc_hash,
        }
    except Exception as exc:
        log.exception("%s_document failed", action)
        return {"error": str(exc)}


def handle_store_document(args: dict) -> dict:
    """Chunk a document, embed it, and store it for semantic retrieval."""
    return _upsert(args, "store")


def handle_update_document(args: dict) -> dict:
    """Replace the stored content of a (source, version) document."""
    return _upsert(args, "update")


def handle_retrieve_context(args: dict) -> dict:
    """Embed a query and return the most relevant stored chunks."""
    query = str(args.get("query", "")).strip()
    if not query:
        return {"error": "query is required", "results": []}
    try:
        top_k = max(1, min(int(args.get("top_k", 5)), MAX_TOP_K))
    except (TypeError, ValueError):
        top_k = 5
    project = str(args.get("project", "")).strip() or None

    try:
        store = get_vector_store()
        query_vector = np.asarray(get_embedder().generate_embeddings([query]))[0]
        # Over-fetch so a project filter can drop hits without starving
        # the result list.
        fetch_k = top_k * FILTER_OVERFETCH if project else top_k
        raw = store.search_vectors(query_vector, k=fetch_k)

        results = []
        for hit in raw:
            meta = hit.get("metadata") or {}
            if project and meta.get("project") != project:
                continue
            results.append(
                {
                    "chunk_id": meta.get("chunk_id", hit.get("id")),
                    "text": meta.get("text", ""),
                    "score": hit.get("score"),
                    "source": meta.get("source"),
                    "authority": meta.get("authority"),
                    "version": meta.get("version"),
                    "project": meta.get("project"),
                }
            )
            if len(results) >= top_k:
                break

        sources = list(dict.fromkeys(r["source"] for r in results if r["source"]))
        return {
            "query": query,
            "results": results,
            "count": len(results),
            "graph_context": _graph_relationships(sources),
        }
    except Exception as exc:
        log.exception("retrieve_context failed")
        return {"error": str(exc), "results": []}


def handle_remove_document(args: dict) -> dict:
    """Remove every chunk stored under (source, version)."""
    source = str(args.get("source", "")).strip()
    if not source:
        return {"error": "source is required"}
    version = str(args.get("version", "")).strip() or "v1"
    try:
        store = get_vector_store()
        existing_ids = _find_matching_ids(store, source, version)
        if not existing_ids:
            return {"status": "not_found", "source": source, "version": version}
        _remove_ids(store, existing_ids)
        _persist(store)
        return {
            "status": "removed",
            "source": source,
            "version": version,
            "removed_chunks": len(existing_ids),
        }
    except Exception as exc:
        log.exception("remove_document failed")
        return {"error": str(exc)}


RETRIEVAL_TOOLS = [
    {
        "name": "store_document",
        "description": (
            "Chunk a document, embed the chunks, and store them for semantic "
            "retrieval. Keyed on (source, version); storing identical content "
            "again is a no-op."
        ),
        "inputSchema": STORE_DOCUMENT,
        "_handler": handle_store_document,
    },
    {
        "name": "retrieve_context",
        "description": (
            "Embed a natural-language query and return the most relevant "
            "stored chunks with scores and provenance, combined with related "
            "knowledge-graph relationships."
        ),
        "inputSchema": RETRIEVE_CONTEXT,
        "_handler": handle_retrieve_context,
    },
    {
        "name": "update_document",
        "description": (
            "Replace the stored content of a document identified by "
            "(source, version). Old chunks are removed and the new content "
            "is re-chunked and re-embedded."
        ),
        "inputSchema": UPDATE_DOCUMENT,
        "_handler": handle_update_document,
    },
    {
        "name": "remove_document",
        "description": (
            "Remove every chunk stored under (source, version) from the "
            "vector store."
        ),
        "inputSchema": REMOVE_DOCUMENT,
        "_handler": handle_remove_document,
    },
]
