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

import copy
import inspect
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple, Union

from ..utils.logging import get_logger
from .context_graph import normalize_temporal_input

__all__ = [
    "ErasureCoordinator",
    "ErasureReceipt",
    "STATUS_ERASED",
    "STATUS_NOT_FOUND",
    "STATUS_NOT_CONFIGURED",
    "STATUS_UNSUPPORTED",
    "STATUS_FAILED",
]

#: The store was reached and the entity's data removed from it. On the vectors
#: leg this means the store accepted the delete for the ids it was given: no
#: backend offers a portable "does this id exist" check, so it is not a count of
#: embeddings that were really there. The memory leg re-queries to confirm and
#: so is the stronger claim of the two.
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
        """Serialize the receipt, deep-copying the per-store results.

        Each store result is copied recursively so the returned payload shares
        no mutable objects with the live receipt: mutating
        ``payload["stores"][name][...]`` (including nested dicts such as a
        vector backend's ``backend_result``) cannot corrupt the audit record.
        """
        return {
            "entity_id": self.entity_id,
            "reason": self.reason,
            "erased_at": self.erased_at,
            "complete": self.complete,
            "stores": {
                name: copy.deepcopy(result) for name, result in self.stores.items()
            },
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

    Note:
        An explicit ``vector_store=False`` also suppresses ``AgentMemory``'s
        own internal vector cascade, not just the coordinator's leg (#1378).
        ``AgentMemory.delete_memory()`` deletes an item's vectors best-effort:
        it catches a vector-store failure, logs it, and still returns ``True``,
        so without this a caller who opted out of the vector leg could still
        have ``memory.vector_store`` mutated underneath them while the receipt
        read ``vectors: not_configured``. ``vector_store=False`` is taken to
        mean "no vector activity at all", so the coordinator passes
        ``skip_vector=True`` through to ``memory.batch_delete()`` in that case,
        and ``receipt.stores["vectors"]["status"]`` stays ``"not_configured"``
        honestly -- the caller opted the vector store out entirely, rather than
        the coordinator having erased it. This only applies when
        ``vector_store=False`` was passed explicitly; when no vector store
        exists anywhere (no ``memory`` was supplied, or ``memory`` has no
        ``vector_store`` attribute), there is nothing to suppress and
        ``memory.batch_delete()`` is called as before.
    """

    def __init__(
        self,
        graph: Optional[Any] = None,
        memory: Optional[Any] = None,
        vector_store: Optional[Any] = None,
    ):
        # `is None` / `is False` rather than truthiness: a real store that
        # defines __bool__ or __len__ (an empty one, say) is falsey while being
        # a perfectly valid store to erase from.
        vector_store_given = vector_store is not None and vector_store is not False
        if graph is None and memory is None and not vector_store_given:
            raise ValueError(
                "ErasureCoordinator needs at least one store to erase from; got "
                f"graph=None, memory=None, vector_store={vector_store!r}"
            )

        self.graph = graph
        self.memory = memory
        # Distinct from `self.vector_store is None`: that's also true when no
        # vector store exists anywhere (no memory, or memory with no
        # vector_store attribute), where there is nothing to suppress and
        # forcing skip_vector onto a duck-typed memory would break callers
        # whose batch_delete() doesn't accept that kwarg.
        self._vector_leg_disabled = vector_store is False
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
        at: Optional[Union[str, int, float, datetime]] = None,
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
            at: When the erasure takes effect, used as the receipt's
                ``erased_at`` and passed to ``purge_node`` so both records
                carry the same instant. Accepts anything ``ContextGraph``
                accepts -- an ISO string, a ``datetime``, or epoch seconds --
                and defaults to now, UTC.
            vector_ids: Explicit vector ids to remove, in addition to the
                ids owned by the entity's memory items, which are always
                included. Defaults to ``[entity_id]``, covering entity-keyed
                embeddings written by something other than ``AgentMemory``.

        Returns:
            An :class:`ErasureReceipt`. Check :attr:`ErasureReceipt.complete`
            before treating the erasure as done.
        """
        # Resolve the timestamp once and hand the *resolved* value to the graph.
        # Passing the caller's `at` through instead would let purge_node take its
        # own now() when `at` is None, so the receipt and the tombstone it
        # attests to would disagree by however long the cascade took.
        erased_at = _normalize_timestamp(at)
        stores: Dict[str, Dict[str, Any]] = {}

        # Outward-in: vectors, then memory, then the graph last.
        #
        # The vector leg must also cover the embeddings owned by memory items.
        # AgentMemory.delete_memory() deletes an item's vectors best-effort: it
        # catches a vector-store failure, logs it, and still returns True, so
        # the memory leg cannot tell a full erasure from one that left the
        # embedding behind. Deleting those ids here instead puts them behind
        # the one leg that reports honestly. Collected before anything is
        # deleted, while the items still exist to be enumerated.
        stores["vectors"] = self._erase_vectors(
            entity_id, self._all_vector_ids(entity_id, vector_ids)
        )
        stores["memory"] = self._erase_memory(entity_id)
        stores["graph"] = self._erase_graph(entity_id, reason, erased_at)

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
        at: Optional[Union[str, int, float, datetime]] = None,
    ) -> List[ErasureReceipt]:
        """Erase several entities, returning one receipt per entity.

        Each entity is erased independently, so one entity's failure does not
        stop the rest. Receipts come back in the order the ids were given.

        The timestamp is resolved once for the whole batch so that every
        receipt and every graph tombstone record the same instant -- a batch
        erasure under a single legal request must not produce tombstones with
        diverging ``purged_at`` values.
        """
        resolved_at = _normalize_timestamp(at)
        return [
            self.erase_entity(entity_id, reason=reason, at=resolved_at)
            for entity_id in entity_ids
        ]

    # Store legs

    def _all_vector_ids(
        self, entity_id: str, vector_ids: Optional[Sequence[str]]
    ) -> List[str]:
        """Caller-supplied vector ids plus the ids owned by memory items.

        Best-effort by design: if memory cannot be enumerated here, the memory
        leg makes the same call moments later and reports the failure, so the
        receipt is still incomplete. Swallowing it there instead would be the
        bug this method exists to fix.

        Collects vector IDs from ALL memory items before deletion. Must call
        find_by_entity with limit=None to get all items, since find_by_entity
        doesn't support offset/cursor and we cannot delete while collecting.
        """
        ids: List[str] = list(vector_ids) if vector_ids is not None else [entity_id]
        if self.memory is None:
            return ids

        seen_vector_ids = set(ids)
        try:
            # Get ALL matching memory items in one call (limit=None).
            # Pagination with deletion happens in _erase_memory(); here we must
            # collect all vector IDs up front before any deletion occurs.
            found = self.memory.find_by_entity(entity_id, limit=None)

            for item in found:
                memory_id = _memory_item_id(item)
                if not memory_id:
                    continue

                for vector_id in self.memory.vector_ids_for(memory_id):
                    if vector_id not in seen_vector_ids:
                        seen_vector_ids.add(vector_id)
                        ids.append(vector_id)
        except Exception as exc:
            self.logger.warning(
                "Could not enumerate memory-owned vector ids for %r: %s; "
                "the memory leg will report the same failure",
                entity_id,
                exc,
            )
        return ids

    def _erase_vectors(
        self, entity_id: str, vector_ids: Optional[Sequence[str]]
    ) -> Dict[str, Any]:
        """Remove entity-keyed embeddings from the bound vector store.

        ``vector_ids`` in the result is the number of ids the store accepted,
        not the number of embeddings that existed: backends delete by id and
        report success either way, with no portable way to ask what was
        actually there. See :data:`STATUS_ERASED`.
        """
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

        accepted, detail = _interpret_delete_result(deleted)
        result: Dict[str, Any] = {
            "status": STATUS_ERASED if accepted else STATUS_FAILED,
            "backend": backend,
            "vector_ids": len(ids),
            "via": method_name,
        }
        # Keep whatever the backend said. Qdrant returns {"status": ...} and
        # Pinecone {"deleted": True}, and that detail is the only account of
        # the delete anyone gets -- dropping it on the floor would leave the
        # receipt less informative than the call it is attesting to.
        if detail is not None:
            result["backend_result"] = detail
        if not accepted:
            self.logger.warning(
                "Vector backend %r reported no deletion for %r: %s",
                backend,
                entity_id,
                detail,
            )
            result["detail"] = "store reported the ids were not deleted"
        return result

    def _erase_memory(self, entity_id: str) -> Dict[str, Any]:
        """Delete every memory item referencing the entity."""
        if self.memory is None:
            return {"status": STATUS_NOT_CONFIGURED}

        deleted = 0
        skip_vector = self._vector_leg_disabled and _accepts_skip_vector(
            self.memory.batch_delete
        )
        if self._vector_leg_disabled and not skip_vector:
            # The class docstring only requires find_by_entity/batch_delete; a
            # duck-typed adapter is not required to support skip_vector. Falling
            # back to the plain call keeps the memory leg working -- the
            # adapter's own cascade (if it has one) just can't be suppressed.
            self.logger.warning(
                "Memory adapter %r has no skip_vector support; its own vector "
                "cascade (if any) could not be suppressed for %r",
                type(self.memory).__name__,
                entity_id,
            )
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

                if skip_vector:
                    removed = self.memory.batch_delete(memory_ids, skip_vector=True)
                else:
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
        at: Optional[Union[str, int, float, datetime]],
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


def _normalize_timestamp(at: Optional[Union[str, int, float, datetime]]) -> str:
    """Render ``at`` exactly as the graph tombstone will record it.

    Reuses ``ContextGraph``'s own normalizer rather than formatting the value
    here, so the receipt and the tombstone written by the same erasure cannot
    disagree about when it happened -- an audit record that contradicts the
    tombstone it attests to is worse than no record. Normalizing up front also
    rejects an unparseable ``at`` before any store is touched, instead of half
    way through the cascade.

    ``None`` resolves to now here rather than being passed along, so the
    default path gets one timestamp for both records instead of two ``now()``
    calls separated by the length of the cascade.
    """
    return normalize_temporal_input(
        at if at is not None else datetime.now(timezone.utc)
    )


def _memory_item_id(item: Any) -> Optional[str]:
    """Pull the identifier out of a memory dict as ``find_by_entity`` returns it."""
    if not isinstance(item, dict):
        return None
    memory_id = item.get("memory_id") or item.get("id")
    return str(memory_id) if memory_id else None


def _accepts_skip_vector(batch_delete: Any) -> bool:
    """True when ``batch_delete`` takes a ``skip_vector`` keyword.

    ``skip_vector`` is an ``AgentMemory``-specific extension, not part of the
    duck-typed contract the class docstring promises (``find_by_entity`` and
    ``batch_delete`` only). Passing it to an adapter that doesn't accept it
    would raise ``TypeError`` and fail the whole memory leg, so this is
    checked before ever passing the kwarg.
    """
    try:
        signature = inspect.signature(batch_delete)
    except (TypeError, ValueError):
        return False
    for parameter in signature.parameters.values():
        if parameter.name == "skip_vector" or parameter.kind == inspect.Parameter.VAR_KEYWORD:
            return True
    return False


#: Dict keys a backend uses to report whether a delete succeeded, and the
#: values that mean it did not. Qdrant returns ``{"status": <UpdateStatus>}``
#: and Pinecone ``{"deleted": True}``; neither is a bool, so a bare
#: ``result is False`` check would call every dict a success.
_DELETE_FAILURE_MARKERS = {
    "deleted": (False,),
    "success": (False,),
    "ok": (False,),
    "acknowledged": (False,),
    "status": ("failed", "error", "failure"),
}


def _interpret_delete_result(result: Any) -> Tuple[bool, Optional[str]]:
    """Decide whether a backend's delete return value reports success.

    Returns ``(accepted, detail)``, where ``detail`` is a serializable
    rendering of the backend's own response to keep in the receipt (``None``
    when there was nothing worth recording).

    ``None`` counts as accepted: a delete implemented as a void method returns
    it on success, and reporting ``failed`` there would be a false alarm --
    the opposite of the honesty this module is for, in the other direction.
    """
    if result is None:
        return True, None
    if isinstance(result, bool):
        return result, None
    if isinstance(result, dict):
        rendered = {key: _stringify(value) for key, value in result.items()}
        for key, failure_values in _DELETE_FAILURE_MARKERS.items():
            if key in result and _is_failure_value(result[key], failure_values):
                return False, rendered
        return True, rendered
    # Anything else (a count, a client response object) is taken at face value;
    # there is no cross-backend contract to interpret it against.
    return True, _stringify(result)


def _is_failure_value(value: Any, failure_values: Tuple[Any, ...]) -> bool:
    """True when a backend's marker value says the delete did not happen.

    Bools are matched by identity so a ``0`` count is not read as ``False``.
    String markers are matched as substrings of the rendered value, because a
    backend may return an enum whose ``str()`` is ``"UpdateStatus.FAILED"``
    rather than a bare ``"failed"``.
    """
    for failure in failure_values:
        if isinstance(failure, bool):
            if value is failure:
                return True
        elif failure in str(value).lower():
            return True
    return False


def _stringify(value: Any) -> Any:
    """Render a backend payload value so the receipt stays serializable.

    Qdrant's status is an enum, which would make ``to_dict()`` output
    unserializable as the audit record it is meant to be.
    """
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


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
