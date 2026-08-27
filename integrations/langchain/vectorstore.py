"""
SemanticaVectorStore — LangChain ``VectorStore`` adapter over Semantica's
hybrid search (``semantica.vector_store.HybridSearch``).
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

from semantica.utils.logging import get_logger

from .retriever import _hit_content, _hit_id, _hit_score, _hit_type, _hit_layers

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Optional: LangChain core
# ---------------------------------------------------------------------------
LANGCHAIN_AVAILABLE = False
LANGCHAIN_IMPORT_ERROR: Optional[str] = None

_VectorStoreBase: Any = object
_Document: Any = None


def _make_document(**kwargs: Any) -> Any:
    if _Document is None:  # pragma: no cover
        raise RuntimeError(LANGCHAIN_IMPORT_ERROR or "langchain-core not installed")
    return _Document(**kwargs)


try:
    from langchain_core.documents import Document as _Document  # type: ignore
    from langchain_core.vectorstores import (
        VectorStore as _VectorStoreBase,  # type: ignore
    )

    LANGCHAIN_AVAILABLE = True
except ImportError:  # pragma: no cover
    LANGCHAIN_IMPORT_ERROR = (
        "langchain-core is not installed. Install with: pip install langchain-core"
    )
    logger.debug(LANGCHAIN_IMPORT_ERROR)


def _document_from_hit(hit: Dict[str, Any], include_score: bool = True) -> Any:
    metadata, _ = _hit_layers(hit)
    node_id = _hit_id(hit)
    doc_meta = {
        **metadata,
        "node_id": node_id,
        "node_type": _hit_type(hit),
    }
    if include_score:
        doc_meta["score"] = _hit_score(hit, default=0.0)
    return _make_document(
        page_content=_hit_content(hit),
        metadata=doc_meta,
    )


class SemanticaVectorStore(_VectorStoreBase):  # type: ignore[misc]
    """Wrap Semantica hybrid search as a LangChain ``VectorStore``.

    Args:
        hybrid: A semantica.vector_store.HybridSearch instance.
        vector_store: Optional Semantica vector store passed through to
            ``HybridSearch.add_texts``.
    """

    hybrid: Any
    vector_store: Any = None

    def __init__(self, hybrid: Any, vector_store: Any = None, **kwargs: Any) -> None:
        if LANGCHAIN_AVAILABLE:
            super().__init__(**kwargs)
        else:
            super().__init__()
        self.hybrid = hybrid
        self.vector_store = vector_store

    # -- required VectorStore API ------------------------------------------
    def add_texts(
        self,
        texts: Iterable[str],
        metadatas: Optional[List[Dict[str, Any]]] = None,
        **kwargs: Any,
    ) -> List[str]:
        """Embed and store texts; return the generated IDs.

        Delegates to the Semantica ``VectorStore.add_documents`` backing the
        HybridSearch instance (or to ``hybrid.vector_store`` if provided).
        """
        if self.vector_store is not None:
            return self.vector_store.add_documents(
                list(texts), metadata=metadatas, **kwargs
            )
        vs = getattr(self.hybrid, "vector_store", None)
        if vs is not None and hasattr(vs, "add_documents"):
            return vs.add_documents(list(texts), metadata=metadatas, **kwargs)
        raise ValueError(
            "SemanticaVectorStore requires a Semantica vector store with "
            "add_documents (pass vector_store=... to the HybridSearch or to "
            "SemanticaVectorStore)"
        )

    def similarity_search(self, query: str, k: int = 4, **kwargs: Any) -> List[Any]:
        """Return documents most similar to the query."""
        return [_document_from_hit(hit) for hit in self.hybrid.search(query, k=k)]

    def similarity_search_with_score(
        self, query: str, k: int = 4, **kwargs: Any
    ) -> List[Any]:
        """Return (document, score) pairs."""
        return [
            (
                _document_from_hit(hit, include_score=False),
                _hit_score(hit, default=0.0),
            )
            for hit in self.hybrid.search(query, k=k)
        ]

    @classmethod
    def from_texts(
        cls,
        texts: List[str],
        embedding: Any = None,
        metadatas: Optional[List[Dict[str, Any]]] = None,
        **kwargs: Any,
    ) -> "SemanticaVectorStore":
        """Build a store from a list of texts (LangChain convention).

        Requires a pre-configured ``hybrid`` instance passed via kwargs.
        """
        hybrid = kwargs.pop("hybrid", None)
        if hybrid is None:
            raise ValueError(
                "SemanticaVectorStore.from_texts requires a 'hybrid' "
                "HybridSearch instance as a keyword argument"
            )
        store = cls(hybrid=hybrid, **kwargs)
        store.add_texts(texts, metadatas=metadatas)
        return store
