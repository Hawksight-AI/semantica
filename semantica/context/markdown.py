"""Shared revision helpers and errors for single-resource Markdown operations."""

import hashlib


class MarkdownResourceNotFoundError(KeyError):
    """Raised when a Markdown operation targets a missing resource."""


class MarkdownIdentityError(ValueError):
    """Raised when frontmatter changes a resource's stable identity."""


class MarkdownRevisionConflictError(ValueError):
    """Raised when a resource changed after an edit session began."""

    def __init__(self, current_revision: str) -> None:
        super().__init__("Markdown resource revision does not match.")
        self.current_revision = current_revision


def markdown_document_revision(source: str) -> str:
    """Return the stable revision token for a canonical Markdown document."""
    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"
