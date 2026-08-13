"""
SemanticaVectorStore — LangChain ``VectorStore`` adapter over Semantica's
hybrid search (``semantica.vector_store.HybridSearch``).
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

from semantica.utils.logging import get_logger

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
        raise RuntimeError(
            LANGCHAIN_IMPORT_ERROR or "langchain-core not installed"
        )
    return _Document(**kwargs)


try:
    from langchain_core.documents import Document as _Document  # type: ignore
    from langchain_core.vectorstores import VectorStore as _VectorStoreBase  # type: ignore

    LANGCHAIN_AVAILABLE = True
except ImportError as exc:  # pragma: no cover
    LANGCHAIN_IMPORT_ERROR = (
        "langchain-core is not installed. Install with: pip install langchain-core"
    )
    logger.debug(LANGCHAIN_IMPORT_ERROR)


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
        super().__init__(**kwargs)
        self.hybrid = hybrid
        self.vector_store = vector_store

    # -- required VectorStore API ------------------------------------------
    def add_texts(
        self,
        texts: Iterable[str],
        metadatas: Optional[List[Dict[str, Any]]] = None,
        **kwargs: Any,
    ) -> List[str]:
        """Embed and store texts; return the generated IDs."""
        ids: List[str] = []
        for idx, text in enumerate(texts):
            meta = metadatas[idx] if metadatas and idx < len(metadatas) else {}
            try:
                node_id = self.hybrid.add_text(text, metadata=meta, **kwargs)
            except TypeError:
                node_id = self.hybrid.add_text(text, metadata=meta)
            ids.append(str(node_id))
        return ids

    def similarity_search(self, query: str, k: int = 4, **kwargs: Any) -> List[Any]:
        """Return documents most similar to the query."""
        return [
            _make_document(page_content=hit.get("content") or hit.get("text") or "",
                           metadata={"node_id": hit.get("node_id") or hit.get("id"),
                                     "node_type": hit.get("node_type") or "node",
                                     "score": float(hit.get("score") or 0.0)})
            for hit in self.hybrid.search(query, k=k)
        ]

    def similarity_search_with_score(
        self, query: str, k: int = 4, **kwargs: Any
    ) -> List[Any]:
        """Return (document, score) pairs."""
        return [
            (
                _make_document(page_content=hit.get("content") or hit.get("text") or "",
                               metadata={"node_id": hit.get("node_id") or hit.get("id"),
                                         "node_type": hit.get("node_type") or "node"}),
                float(hit.get("score") or 0.0),
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
