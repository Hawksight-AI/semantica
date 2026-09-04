"""Single-resource Markdown access for Explorer."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable, Dict, Optional, Protocol, TypeVar

import yaml

from ..context.agent_memory import AgentMemory
from ..context.context_graph import ContextGraph
from ..context.markdown import (
    MarkdownIdentityError,
    MarkdownResourceNotFoundError,
    MarkdownRevisionConflictError,
    markdown_document_revision,
)


class MarkdownResourceKind(str, Enum):
    CONTEXT_NODE = "context-node"
    AGENT_MEMORY = "agent-memory"


@dataclass(frozen=True)
class MarkdownResourceRef:
    kind: MarkdownResourceKind
    id: str


@dataclass(frozen=True)
class MarkdownDocument:
    resource: MarkdownResourceRef
    source: str
    body: str
    revision: str


@dataclass(frozen=True)
class MarkdownApplyResult(MarkdownDocument):
    changed: bool


class MarkdownResourceError(Exception):
    """Base class for safe, structured Explorer Markdown failures."""

    code = "markdown_resource_error"

    def __init__(
        self,
        message: str,
        *,
        field: Optional[str] = None,
        current_revision: Optional[str] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.field = field
        self.current_revision = current_revision


class MarkdownResourceNotFound(MarkdownResourceError):
    code = "markdown_resource_not_found"


class InvalidMarkdownFrontmatter(MarkdownResourceError):
    code = "invalid_markdown_frontmatter"


class ResourceIdentityMismatch(MarkdownResourceError):
    code = "resource_identity_mismatch"


class MarkdownRevisionConflict(MarkdownResourceError):
    code = "markdown_revision_conflict"


class MarkdownSaveFailed(MarkdownResourceError):
    code = "markdown_save_failed"


class MarkdownAdapter(Protocol):
    def export(self, resource_id: str) -> str:
        ...

    def apply(self, resource_id: str, source: str, expected_revision: str) -> bool:
        ...


_Result = TypeVar("_Result")


def _translate_domain_errors(operation: Callable[[], _Result]) -> _Result:
    try:
        return operation()
    except MarkdownResourceNotFoundError as exc:
        raise MarkdownResourceNotFound(str(exc.args[0])) from exc
    except MarkdownRevisionConflictError as exc:
        raise MarkdownRevisionConflict(
            "This item changed after editing began. Reload the latest "
            "version before applying.",
            current_revision=exc.current_revision,
        ) from exc
    except MarkdownIdentityError as exc:
        raise ResourceIdentityMismatch(str(exc), field="id") from exc
    except ValueError as exc:
        raise InvalidMarkdownFrontmatter(_safe_validation_message(exc)) from exc


class ContextGraphNodeMarkdownAdapter:
    def __init__(self, graph: ContextGraph) -> None:
        self._graph = graph

    def export(self, resource_id: str) -> str:
        return _translate_domain_errors(
            lambda: self._graph.export_node_markdown(resource_id)
        )

    def apply(self, resource_id: str, source: str, expected_revision: str) -> bool:
        return _translate_domain_errors(
            lambda: self._graph.apply_node_markdown(
                resource_id,
                source,
                expected_revision=expected_revision,
            )
        )


class AgentMemoryItemMarkdownAdapter:
    def __init__(self, memory: AgentMemory) -> None:
        self._memory = memory

    def export(self, resource_id: str) -> str:
        return _translate_domain_errors(
            lambda: self._memory.export_item_markdown(resource_id)
        )

    def apply(self, resource_id: str, source: str, expected_revision: str) -> bool:
        return _translate_domain_errors(
            lambda: self._memory.apply_item_markdown(
                resource_id,
                source,
                expected_revision=expected_revision,
            )
        )


def _safe_validation_message(exc: ValueError) -> str:
    if isinstance(exc.__cause__, yaml.YAMLError):
        return "Markdown frontmatter contains invalid YAML."
    return str(exc)


def document_revision(source: str) -> str:
    """Return the stable revision token for canonical Markdown.

    Args:
        source: Canonical Markdown source.

    Returns:
        A SHA-256 revision token suitable for optimistic concurrency checks.
    """
    return markdown_document_revision(source)


def markdown_body(source: str) -> str:
    """Extract the body from canonical Markdown emitted by a domain model."""
    lines = source.splitlines(keepends=True)
    if not lines or lines[0].rstrip("\r\n") != "---":
        raise MarkdownSaveFailed("The resource produced invalid canonical Markdown.")
    closing_index = next(
        (
            index
            for index, line in enumerate(lines[1:], start=1)
            if line.rstrip("\r\n") == "---"
        ),
        None,
    )
    if closing_index is None:
        raise MarkdownSaveFailed("The resource produced invalid canonical Markdown.")
    body = "".join(lines[closing_index + 1 :])
    if body.startswith("\r\n"):
        return body[2:]
    if body.startswith("\n"):
        return body[1:]
    return body


class MarkdownResourceRegistry:
    """Route Markdown operations to their owning domain models."""

    def __init__(
        self,
        context_graph: ContextGraph,
        agent_memory: Optional[AgentMemory] = None,
    ) -> None:
        self._adapters: Dict[MarkdownResourceKind, MarkdownAdapter] = {
            MarkdownResourceKind.CONTEXT_NODE: ContextGraphNodeMarkdownAdapter(
                context_graph
            )
        }
        if agent_memory is not None:
            self._adapters[
                MarkdownResourceKind.AGENT_MEMORY
            ] = AgentMemoryItemMarkdownAdapter(agent_memory)

    def _adapter(self, kind: MarkdownResourceKind) -> MarkdownAdapter:
        adapter = self._adapters.get(kind)
        if adapter is None:
            raise MarkdownResourceNotFound(
                f"Markdown resource kind {kind.value!r} is not available."
            )
        return adapter

    def read(self, ref: MarkdownResourceRef) -> MarkdownDocument:
        """Read one resource as canonical Markdown.

        Args:
            ref: Explicit resource kind and stable identifier.

        Returns:
            The canonical source, body, and current revision.

        Raises:
            MarkdownResourceError: If the resource is unavailable or invalid.
        """
        try:
            source = self._adapter(ref.kind).export(ref.id)
        except MarkdownResourceError:
            raise
        except Exception as exc:
            raise MarkdownSaveFailed(
                "The Markdown resource could not be read."
            ) from exc
        return MarkdownDocument(
            resource=ref,
            source=source,
            body=markdown_body(source),
            revision=document_revision(source),
        )

    def apply(
        self,
        ref: MarkdownResourceRef,
        markdown: str,
        expected_revision: str,
    ) -> MarkdownApplyResult:
        """Apply validated Markdown to one existing resource.

        Args:
            ref: Explicit resource kind and stable identifier.
            markdown: Replacement canonical Markdown.
            expected_revision: Revision observed when editing began.

        Returns:
            The saved canonical document and whether it changed.

        Raises:
            MarkdownResourceError: If validation, identity, persistence, or
                revision checks fail.
        """
        try:
            changed = self._adapter(ref.kind).apply(
                ref.id,
                markdown,
                expected_revision,
            )
        except MarkdownResourceError:
            raise
        except Exception as exc:
            raise MarkdownSaveFailed(
                "The edit could not be applied. The existing item was not changed."
            ) from exc

        saved = self.read(ref)
        return MarkdownApplyResult(
            resource=saved.resource,
            source=saved.source,
            body=saved.body,
            revision=saved.revision,
            changed=changed,
        )
