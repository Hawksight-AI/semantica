"""
SemanticaVectorStore — Thin adapter over semantica.vector_store.VectorStore.
"""

from __future__ import annotations

import logging
from typing import Any, Iterable, List, Optional, Tuple, Type

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional: LangChain VectorStore base class
# ---------------------------------------------------------------------------
LANGCHAIN_AVAILABLE = False
_VectorStoreBase: Any = object

try:
    from langchain_core.vectorstores import VectorStore as _LCVectorStore
    from langchain_core.documents import Document as LCDocument

    _VectorStoreBase = _LCVectorStore
    LANGCHAIN_AVAILABLE = True
except ImportError:
    # Minimal stand-in for Document when langchain is absent
    class LCDocument:  # type: ignore
        def __init__(self, page_content: str, metadata: dict | None = None) -> None:
            self.page_content = page_content
            self.metadata = metadata or {}


class SemanticaVectorStore(_VectorStoreBase):  # type: ignore[misc]
    """
    SemanticaVectorStore wraps semantica.vector_store.VectorStore.

    Can be dropped into any existing RetrievalQA or LCEL chain expecting a VectorStore.
    """

    def __init__(
        self,
        vector_store: Any = None,
        embedding: Any = None,
        **kwargs: Any,
    ) -> None:
        """
        Initialize SemanticaVectorStore.

        Parameters
        ----------
        vector_store:
            An instance of ``semantica.vector_store.VectorStore``. Created automatically when None.
        embedding:
            An optional LangChain Embeddings instance to generate vectors.
        """
        if LANGCHAIN_AVAILABLE:
            super().__init__()

        from semantica.vector_store import VectorStore

        if vector_store is None:
            self.vector_store = VectorStore(**kwargs)
        else:
            self.vector_store = vector_store

        self.embedding = embedding
        if embedding is not None:
            if hasattr(embedding, "embed_query"):
                self.vector_store.embed = embedding.embed_query
            if hasattr(embedding, "embed_documents"):
                self.vector_store.embed_batch = embedding.embed_documents

    def add_texts(
        self,
        texts: Iterable[str],
        metadatas: Optional[List[dict]] = None,
        **kwargs: Any,
    ) -> List[str]:
        """
        Add texts to the Semantica VectorStore.
        """
        texts_list = list(texts)
        # Ensure texts are preserved in the metadata as "text" and "content" fields
        metadatas_list = []
        for i, text in enumerate(texts_list):
            meta = metadatas[i].copy() if metadatas and i < len(metadatas) else {}
            meta.setdefault("text", text)
            meta.setdefault("content", text)
            metadatas_list.append(meta)

        return self.vector_store.add_documents(texts_list, metadata=metadatas_list, **kwargs)

    def similarity_search_with_score(
        self,
        query: str,
        k: int = 4,
        **kwargs: Any,
    ) -> List[Tuple[LCDocument, float]]:
        """
        Search for similar documents and return they scores.
        """
        results = self.vector_store.search(query, limit=k, **kwargs)

        docs_with_scores = []
        for res in results:
            metadata = res.get("metadata", {})
            content = metadata.get("text", metadata.get("content", res.get("content", "")))
            # If no content is found, fall back to stringified representation
            if not content:
                content = str(res)

            doc = LCDocument(page_content=content, metadata=metadata)
            score = float(res.get("score", 0.0))
            docs_with_scores.append((doc, score))

        return docs_with_scores

    def similarity_search(
        self,
        query: str,
        k: int = 4,
        **kwargs: Any,
    ) -> List[LCDocument]:
        """
        Search for similar documents.
        """
        results = self.similarity_search_with_score(query, k=k, **kwargs)
        return [doc for doc, _ in results]

    @classmethod
    def from_texts(
        cls,
        texts: List[str],
        embedding: Any = None,
        metadatas: Optional[List[dict]] = None,
        **kwargs: Any,
    ) -> SemanticaVectorStore:
        """
        Create a SemanticaVectorStore from raw texts.
        """
        instance = cls(embedding=embedding, **kwargs)
        instance.add_texts(texts, metadatas=metadatas)
        return instance
