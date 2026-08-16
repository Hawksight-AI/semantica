"""
Cross-store erasure coordination.

``ContextGraph.purge_node()`` is graph-scope by design (#957): it removes the
node and leaves a tombstone, but any copy of the same content held in
``AgentMemory`` or in a bound vector store is untouched. That makes purge one
step of an erasure workflow rather than the whole of it, and leaves the caller
to drive the remaining steps by hand -- with no record of which of them
actually succeeded.

:class:`ErasureCoordinator` drives the cascade across the stores it is given
and returns an :class:`ErasureReceipt` describing what was reached and what was
not. It *composes* the existing public APIs; nothing in ``context_graph.py`` or
``agent_memory.py`` changes, and ``ContextGraph`` keeps its graph-scope
contract.

The property that matters is honest partial reporting. Three vector backends
(FAISS, Milvus, Weaviate) expose no delete at all, so erasure is genuinely not
completable on them today. The receipt says ``unsupported`` for those rather
than reporting a success it did not achieve -- a receipt that reads
"graph: erased, memory: 14 erased, vectors: unsupported on faiss" is
actionable; a bare ``True`` is a compliance liability.

Example:
    >>> from semantica.context import ContextGraph, AgentMemory
    >>> from semantica.context.erasure import ErasureCoordinator
    >>> coordinator = ErasureCoordinator(graph=graph, memory=memory)
    >>> receipt = coordinator.erase_entity(
    ...     "customer-4471", reason="GDPR Art. 17 request #882"
    ... )
    >>> receipt.complete
    False
    >>> receipt.stores["vectors"]["status"]
    'unsupported'
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple, Union

from ..utils.logging import get_logger
from .context_graph import _normalize_temporal_input

__all__ = [
    "ErasureCoordinator",
    "ErasureReceipt",
    "STATUS_ERASED",
    "STATUS_NOT_FOUND",
    "STATUS_NOT_CONFIGURED",
    "STATUS_UNSUPPORTED",
    "STATUS_FAILED",
]

#: The store was reached and the entity's data removed from it.
STATUS_ERASED = "erased"
#: The store was reached and held nothing for this entity.
STATUS_NOT_FOUND = "not_found"
#: No such store was bound to the coordinator. Normal, not a failure.
STATUS_NOT_CONFIGURED = "not_configured"
#: The store exists but cannot delete -- e.g. a vector backend with no delete
#: method. Deliberately distinct from ``failed``: retrying will not help.
STATUS_UNSUPPORTED = "unsupported"
#: The store was reached and the deletion did not succeed.
STATUS_FAILED = "failed"

#: Statuses that leave data behind. A receipt containing any of these is not
#: complete, and the shortfall has to be handled out of band.
_INCOMPLETE_STATUSES = frozenset({STATUS_UNSUPPORTED, STATUS_FAILED})

#: Page size for the memory sweep. See ``_erase_memory`` for why the sweep
#: loops rather than passing one large limit.
_MEMORY_SWEEP_BATCH = 500

logger = get_logger("erasure")


@dataclass
class ErasureReceipt:
    """Auditable record of one entity's erasure across every bound store.

    Attributes:
        entity_id: The entity the erasure was requested for.
        reason: Why it was erased, e.g. an erasure-request reference.
        erased_at: ISO-8601 timestamp of the erasure.
        stores: Per-store outcome keyed by ``"vectors"``, ``"memory"`` and
            ``"graph"``, each a dict with at least a ``status`` key drawn from
            the ``STATUS_*`` constants in this module.
    """

    entity_id: str
    reason: Optional[str] = None
    erased_at: str = ""
    stores: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    @property
    def complete(self) -> bool:
        """True when no bound store was left holding data.

        ``not_configured`` and ``not_found`` count as complete -- a store that
        was never bound, or that held nothing, leaves no residue. Only
        ``unsupported`` and ``failed`` mean data survived the erasure.
        """
        return not self.incomplete_stores

    @property
    def incomplete_stores(self) -> List[str]:
        """Names of the stores that may still hold the entity's data."""
        return [
            name
            for name, result in self.stores.items()
            if result.get("status") in _INCOMPLETE_STATUSES
        ]

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the receipt, deep-copying the per-store results."""
        return {
            "entity_id": self.entity_id,
            "reason": self.reason,
            "erased_at": self.erased_at,
            "complete": self.complete,
            "stores": {name: dict(result) for name, result in self.stores.items()},
        }


class ErasureCoordinator:
    """Drives erasure of an entity across the graph, memory and vector stores.

    Every store is optional; a store that is not supplied reports
    ``not_configured`` rather than being silently skipped, so the receipt still
    shows the full shape of the workflow.

    Args:
        graph: A :class:`~semantica.context.ContextGraph` (or anything exposing
            ``purge_node``).
        memory: An :class:`~semantica.context.AgentMemory` (or anything
            exposing ``find_by_entity`` and ``batch_delete``).
        vector_store: Vector store holding entity-keyed embeddings. Defaults to
            ``memory.vector_store`` when a memory is supplied, and stays
            overridable for deployments that bind a store the memory does not
            own. Pass ``False`` to disable the vector leg entirely.

    Note:
        Erasure runs outward-in -- vectors, then memory, then the graph. The
        graph tombstone is the durable attestation that an erasure happened, so
        writing it first would let a crash mid-cascade leave a record claiming
        more than actually occurred. Erasing the graph last means a partial
        failure leaves the node present and the receipt incomplete, which is
        recoverable and honest.
    """

    def __init__(
        self,
        graph: Optional[Any] = None,
        memory: Optional[Any] = None,
        vector_store: Optional[Any] = None,
    ):
        if graph is None and memory is None and not vector_store:
            raise ValueError(
                "ErasureCoordinator needs at least one store to erase from; "
                "got graph=None, memory=None, vector_store=None"
            )

        self.graph = graph
        self.memory = memory
        if vector_store is False:
            self.vector_store: Optional[Any] = None
        elif vector_store is not None:
            self.vector_store = vector_store
        else:
            self.vector_store = getattr(memory, "vector_store", None)

        self.logger = logger

    def erase_entity(
        self,
        entity_id: str,
        reason: Optional[str] = None,
        at: Optional[Union[str, datetime]] = None,
        vector_ids: Optional[Sequence[str]] = None,
    ) -> ErasureReceipt:
        """Erase one entity from every bound store and return a receipt.

        A store that cannot be erased from is recorded in the receipt and the
        cascade continues -- partial failure is a result, not an exception.
        Aborting on the first failure would leave a half-erased state with no
        record of which half.

        Args:
            entity_id: Entity to erase. Interpreted as a graph node id, an
                ``entities[].id`` in memory items, and a vector id.
            reason: Why it was erased, e.g. an erasure-request reference.
                Recorded in the receipt and in the graph tombstone.
            at: When the erasure takes effect, passed through to
                ``purge_node`` and used as the receipt's ``erased_at``.
                Defaults to now, UTC.
            vector_ids: Explicit vector ids to remove. Defaults to
                ``[entity_id]``, which covers entity-keyed embeddings written
                by something other than ``AgentMemory``; vectors owned by
                memory items are removed by the memory leg's own cascade.

        Returns:
            An :class:`ErasureReceipt`. Check :attr:`ErasureReceipt.complete`
            before treating the erasure as done.
        """
        erased_at = _normalize_timestamp(at)
        stores: Dict[str, Dict[str, Any]] = {}

        # Outward-in: vectors, then memory, then the graph last.
        stores["vectors"] = self._erase_vectors(entity_id, vector_ids)
        stores["memory"] = self._erase_memory(entity_id)
        stores["graph"] = self._erase_graph(entity_id, reason, at)

        receipt = ErasureReceipt(
            entity_id=entity_id,
            reason=reason,
            erased_at=erased_at,
            stores=stores,
        )

        if receipt.complete:
            self.logger.info(
                "Erased %r across %d store(s)%s",
                entity_id,
                len(stores),
                f" ({reason})" if reason else "",
            )
        else:
            self.logger.warning(
                "Erasure of %r is incomplete; these stores may still hold it: %s",
                entity_id,
                ", ".join(receipt.incomplete_stores),
            )
        return receipt

    def erase_entities(
        self,
        entity_ids: Iterable[str],
        reason: Optional[str] = None,
        at: Optional[Union[str, datetime]] = None,
    ) -> List[ErasureReceipt]:
        """Erase several entities, returning one receipt per entity.

        Each entity is erased independently, so one entity's failure does not
        stop the rest. Receipts come back in the order the ids were given.
        """
        return [
            self.erase_entity(entity_id, reason=reason, at=at)
            for entity_id in entity_ids
        ]

    # Store legs

    def _erase_vectors(
        self, entity_id: str, vector_ids: Optional[Sequence[str]]
    ) -> Dict[str, Any]:
        """Remove entity-keyed embeddings from the bound vector store."""
        if self.vector_store is None:
            return {"status": STATUS_NOT_CONFIGURED}

        ids = list(vector_ids) if vector_ids is not None else [entity_id]
        backend = _vector_backend_name(self.vector_store)
        if not ids:
            return {"status": STATUS_NOT_FOUND, "backend": backend}

        method_name, target = _vector_delete_capability(self.vector_store)
        if method_name is None:
            # FAISS, Milvus and Weaviate expose no delete at all; FAISS in
            # particular cannot remove from a flat index without a rebuild.
            self.logger.warning(
                "Vector backend %r exposes no delete; %d vector id(s) for %r "
                "were not erased",
                backend,
                len(ids),
                entity_id,
            )
            return {
                "status": STATUS_UNSUPPORTED,
                "backend": backend,
                "vector_ids": len(ids),
                "detail": (
                    "backend exposes no delete()/delete_vectors(); "
                    "removal requires an index rebuild or an out-of-band process"
                ),
            }

        try:
            deleted = getattr(target, method_name)(ids)
        except NotImplementedError as exc:
            # The VectorStore facade declares delete_vectors() unconditionally
            # and only fails on the call when its backend cannot delete.
            self.logger.warning(
                "Vector backend %r cannot delete %d id(s) for %r: %s",
                backend,
                len(ids),
                entity_id,
                exc,
            )
            return {
                "status": STATUS_UNSUPPORTED,
                "backend": backend,
                "vector_ids": len(ids),
                "detail": str(exc),
            }
        except Exception as exc:
            self.logger.warning(
                "Vector deletion failed for %r on backend %r: %s",
                entity_id,
                backend,
                exc,
                exc_info=True,
            )
            return {
                "status": STATUS_FAILED,
                "backend": backend,
                "vector_ids": len(ids),
                "detail": f"{type(exc).__name__}: {exc}",
            }

        if deleted is False:
            self.logger.warning(
                "Vector backend %r reported no deletion for %r", backend, entity_id
            )
            return {
                "status": STATUS_FAILED,
                "backend": backend,
                "vector_ids": len(ids),
                "detail": "store reported the ids were not deleted",
            }

        return {
            "status": STATUS_ERASED,
            "backend": backend,
            "vector_ids": len(ids),
            "via": method_name,
        }

    def _erase_memory(self, entity_id: str) -> Dict[str, Any]:
        """Delete every memory item referencing the entity."""
        if self.memory is None:
            return {"status": STATUS_NOT_CONFIGURED}

        deleted = 0
        try:
            # Sweep in pages until dry rather than passing one large limit:
            # ``find_by_entity`` has historically defaulted to ``limit=10`` and
            # truncated silently, and a single large number is only correct
            # until someone exceeds it. Deleting as we go means the next page
            # is the remainder.
            while True:
                found = self.memory.find_by_entity(entity_id, limit=_MEMORY_SWEEP_BATCH)
                if not found:
                    break

                memory_ids = [
                    memory_id
                    for memory_id in (_memory_item_id(item) for item in found)
                    if memory_id
                ]
                if not memory_ids:
                    self.logger.warning(
                        "Memory returned %d item(s) for %r with no identifier; "
                        "cannot delete them",
                        len(found),
                        entity_id,
                    )
                    return {
                        "status": STATUS_FAILED,
                        "items": deleted,
                        "residual": len(found),
                        "detail": "memory items carry no 'memory_id'",
                    }

                removed = self.memory.batch_delete(memory_ids)
                deleted += removed
                if removed == 0:
                    # No progress: another page would return the same items.
                    self.logger.warning(
                        "Memory sweep for %r stalled with %d item(s) remaining",
                        entity_id,
                        len(found),
                    )
                    return {
                        "status": STATUS_FAILED,
                        "items": deleted,
                        "residual": len(found),
                        "detail": "batch_delete removed nothing for a non-empty page",
                    }
                if len(found) < _MEMORY_SWEEP_BATCH:
                    break

            # Re-query once rather than trusting the loop's own bookkeeping;
            # this is what keeps the leg's `failed` status honest.
            residual = self.memory.find_by_entity(entity_id, limit=_MEMORY_SWEEP_BATCH)
        except Exception as exc:
            self.logger.warning(
                "Memory erasure failed for %r after %d item(s): %s",
                entity_id,
                deleted,
                exc,
                exc_info=True,
            )
            return {
                "status": STATUS_FAILED,
                "items": deleted,
                "detail": f"{type(exc).__name__}: {exc}",
            }

        if residual:
            self.logger.warning(
                "Memory still holds %d item(s) for %r after erasure",
                len(residual),
                entity_id,
            )
            return {
                "status": STATUS_FAILED,
                "items": deleted,
                "residual": len(residual),
                "detail": "items referencing the entity survived the sweep",
            }

        if deleted == 0:
            return {"status": STATUS_NOT_FOUND, "items": 0}
        return {"status": STATUS_ERASED, "items": deleted}

    def _erase_graph(
        self,
        entity_id: str,
        reason: Optional[str],
        at: Optional[Union[str, datetime]],
    ) -> Dict[str, Any]:
        """Purge the node, and with it every edge that touches it."""
        if self.graph is None:
            return {"status": STATUS_NOT_CONFIGURED}

        try:
            # Counted before the purge because the edges are gone afterwards.
            edge_count = _incident_edge_count(self.graph, entity_id)
            purged = self.graph.purge_node(entity_id, reason=reason, at=at)
        except Exception as exc:
            self.logger.warning(
                "Graph purge failed for %r: %s", entity_id, exc, exc_info=True
            )
            return {
                "status": STATUS_FAILED,
                "detail": f"{type(exc).__name__}: {exc}",
            }

        if not purged:
            return {"status": STATUS_NOT_FOUND, "nodes": 0, "edges": 0}
        return {"status": STATUS_ERASED, "nodes": 1, "edges": edge_count}


# Helpers


def _normalize_timestamp(at: Optional[Union[str, datetime]]) -> str:
    """Render ``at`` exactly as the graph tombstone will record it.

    Reuses ``ContextGraph``'s own normalizer rather than formatting the value
    here, so the receipt and the tombstone written by the same erasure cannot
    disagree about when it happened -- an audit record that contradicts the
    tombstone it attests to is worse than no record. Normalizing up front also
    rejects an unparseable ``at`` before any store is touched, instead of half
    way through the cascade.
    """
    if at is None:
        return datetime.now(timezone.utc).isoformat()
    return _normalize_temporal_input(at)


def _memory_item_id(item: Any) -> Optional[str]:
    """Pull the identifier out of a memory dict as ``find_by_entity`` returns it."""
    if not isinstance(item, dict):
        return None
    memory_id = item.get("memory_id") or item.get("id")
    return str(memory_id) if memory_id else None


def _vector_delete_capability(store: Any) -> Tuple[Optional[str], Any]:
    """Find the delete method to call, and the object to call it on.

    Returns ``(None, target)`` when no delete surface exists, which is the
    ``unsupported`` case.

    The ``VectorStore`` facade declares ``delete_vectors()`` for every backend
    and only raises ``NotImplementedError`` once called, so probing the facade
    alone cannot tell a deletable backend from a delete-less one -- hence the
    look at the backend it wraps. Probing rather than calling-and-catching also
    keeps a missing method distinguishable from an ``AttributeError`` raised
    *inside* a working one, which is exactly where guessing wrong would produce
    a false clean bill of health.
    """
    target = getattr(store, "_backend_store", None) or store
    for name in ("delete_vectors", "delete"):
        if callable(getattr(target, name, None)):
            return name, target
    return None, target


def _vector_backend_name(store: Any) -> str:
    """Best-effort backend label for the receipt."""
    backend = getattr(store, "backend", None)
    if isinstance(backend, str) and backend:
        return backend
    inner = getattr(store, "_backend_store", None)
    return type(inner if inner is not None else store).__name__


def _incident_edge_count(graph: Any, node_id: str) -> int:
    """Count edges touching ``node_id`` through the graph's public API."""
    find_edges = getattr(graph, "find_edges", None)
    if not callable(find_edges):
        return 0
    return sum(
        1
        for edge in find_edges()
        if edge.get("source") == node_id or edge.get("target") == node_id
    )
