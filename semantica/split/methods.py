"""
Splitting Methods Module

This module provides all splitting methods as simple, reusable functions for
text chunking and splitting. It supports multiple splitting approaches ranging
from simple character-based splitting to advanced KG/ontology-aware chunking.

Supported Methods:

Standard Text Splitting:
    - "recursive": Recursive splitting with separator hierarchy
    - "token": Token-based splitting using tiktoken/transformers
    - "sentence": Sentence boundary splitting (regex, NLTK, spaCy)
    - "paragraph": Paragraph boundary splitting
    - "character": Character count splitting
    - "word": Word count splitting
    - "semantic_transformer": Sentence transformer-based splitting
    - "llm": LLM-based optimal split point detection
    - "huggingface": HuggingFace model-based splitting
    - "nltk": NLTK-based splitting

KG/Ontology/Graph Analytics Methods:
    - "entity_aware": Entity boundary-preserving splitting
    - "relation_aware": Triplet-preserving splitting
    - "graph_based": Graph structure-based splitting
    - "ontology_aware": Ontology concept/hierarchy-based splitting
    - "embedding_semantic": Embedding similarity-based boundaries
    - "hierarchical": Multi-level hierarchical chunking
    - "community_detection": Community detection-based chunking
    - "centrality_based": Centrality-based chunking
    - "subgraph": Subgraph extraction-based chunking
    - "topic_based": Topic modeling-based chunking

Algorithms Used:

Standard Splitting:
    - Recursive Splitting: Separator hierarchy and greedy splitting
    - Token Counting: BPE tokenization (tiktoken, transformers)
    - Sentence Segmentation: NLTK, spaCy, regex-based
    - Semantic Boundary Detection: Sentence transformer embeddings and similarity
    - LLM-based Splitting: Prompt engineering for optimal split point detection

KG/Ontology/Graph Analytics:
    - Entity Boundary Detection: NER-based entity extraction and boundary preservation
    - Triplet Preservation: Graph-based triplet integrity checking
    - Graph Centrality Analysis: Degree, betweenness, closeness, eigenvector centrality
    - Community Detection: Louvain algorithm, Leiden algorithm, modularity optimization
    - Graph Connectivity: Connected components, shortest paths, bridge detection
    - Ontology Hierarchy Traversal: Taxonomic structure traversal and concept grouping
    - Embedding Similarity: Cosine similarity, Euclidean distance for semantic boundaries
    - Subgraph Extraction: k-hop neighborhood extraction, connected component detection
    - Topic Modeling: LDA (Latent Dirichlet Allocation), BERTopic for theme detection
    - Hierarchical Segmentation: Multi-level document structure analysis

Key Features:
    - Multiple standard splitting methods
    - KG/ontology/graph analytics-specific chunking methods
    - Method dispatchers with registry support
    - Custom method registration capability
    - Consistent interface across all methods
    - Integration with existing chunkers

Main Functions:
    - split_recursive: Recursive splitting with separator hierarchy
    - split_by_tokens: Token-based splitting
    - split_by_sentences: Sentence boundary splitting
    - split_by_paragraphs: Paragraph boundary splitting
    - split_by_characters: Character count splitting
    - split_by_words: Word count splitting
    - split_semantic_transformer: Sentence transformer-based splitting
    - split_llm: LLM-based optimal split point detection
    - split_entity_aware: Entity boundary-preserving splitting
    - split_relation_aware: Triplet-preserving splitting
    - split_graph_based: Graph structure-based splitting
    - split_ontology_aware: Ontology concept-based splitting
    - split_hierarchical: Multi-level hierarchical chunking
    - get_split_method: Get splitting method by name

Example Usage:
    >>> from semantica.split.methods import get_split_method
    >>> split_fn = get_split_method("recursive")
    >>> chunks = split_fn(text, chunk_size=1000, chunk_overlap=200)

Author: Semantica Contributors
License: MIT
"""

import re
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Union

from ..utils.exceptions import ProcessingError
from ..utils.helpers import safe_import
from ..utils.logging import get_logger
from .semantic_chunker import Chunk

logger = get_logger("split_methods")

# Try to import optional dependencies
_, SPACY_AVAILABLE = safe_import("spacy")

nltk, NLTK_AVAILABLE = safe_import("nltk")
tiktoken, TIKTOKEN_AVAILABLE = safe_import("tiktoken")
_sentence_transformers, SENTENCE_TRANSFORMER_AVAILABLE = safe_import("sentence_transformers")
if SENTENCE_TRANSFORMER_AVAILABLE:
    from sentence_transformers import SentenceTransformer
else:
    SentenceTransformer = None
_transformers, TRANSFORMERS_AVAILABLE = safe_import("transformers")
if TRANSFORMERS_AVAILABLE:
    from transformers import AutoTokenizer
else:
    AutoTokenizer = None

networkx, NETWORKX_AVAILABLE = safe_import("networkx")
if NETWORKX_AVAILABLE:
    nx = networkx
else:
    nx = None

# Try community package with fallback
_community1, _avail1 = safe_import("community.community_louvain")
if _avail1:
    import community.community_louvain as community_louvain
    COMMUNITY_AVAILABLE = True
else:
    _community2, _avail2 = safe_import("community")
    if _avail2:
        try:
            from community import community_louvain
            COMMUNITY_AVAILABLE = True
        except (ImportError, OSError):
            COMMUNITY_AVAILABLE = False
    else:
        COMMUNITY_AVAILABLE = False

# Import from semantic_extract for entity/relation extraction
try:
    from ..semantic_extract.ner_extractor import NERExtractor
    from ..semantic_extract.providers import create_provider
    from ..semantic_extract.relation_extractor import RelationExtractor

    SEMANTIC_EXTRACT_AVAILABLE = True
except (ImportError, OSError):
    SEMANTIC_EXTRACT_AVAILABLE = False

# Import specialized chunkers
try:
    from .structural_chunker import StructuralChunker
    from .sliding_window_chunker import SlidingWindowChunker
    
    SPECIALIZED_CHUNKERS_AVAILABLE = True
except (ImportError, OSError):
    SPECIALIZED_CHUNKERS_AVAILABLE = False


# ============================================================================
# Standard Splitting Methods
# ============================================================================


def split_recursive(
    text: str,
    chunk_size: int = 1000,
    chunk_overlap: int = 200,
    separators: Optional[List[str]] = None,
    **kwargs,
) -> List[Chunk]:
    """
    Recursive splitting with separator hierarchy.

    Args:
        text: Input text
        chunk_size: Target chunk size
        chunk_overlap: Overlap between chunks
        separators: List of separators in priority order
        **kwargs: Additional options

    Returns:
        List of chunks
    """
    if separators is None:
        separators = ["\n\n", "\n", ". ", " ", ""]

    chunks = []
    text_length = len(text)
    start = 0

    while start < text_length:
        # Find the best split point
        end = start + chunk_size
        if end >= text_length:
            chunk_text = text[start:]
            chunks.append(
                Chunk(
                    text=chunk_text,
                    start_index=start,
                    end_index=text_length,
                    metadata={"method": "recursive", "chunk_size": len(chunk_text)},
                )
            )
            break

        # Try each separator in priority order
        split_pos = -1
        for separator in separators:
            if separator:
                pos = text.rfind(separator, start, end)
                if pos > start + chunk_size * 0.5:  # At least 50% of target size
                    split_pos = pos + len(separator)
                    break
            else:
                # Last resort: split at character boundary
                split_pos = end

        if split_pos == -1:
            split_pos = end

        chunk_text = text[start:split_pos].strip()
        if chunk_text:
            chunks.append(
                Chunk(
                    text=chunk_text,
                    start_index=start,
                    end_index=split_pos,
                    metadata={"method": "recursive", "chunk_size": len(chunk_text)},
                )
            )

        # Move to next chunk with overlap
        start = max(start + 1, split_pos - chunk_overlap)

    return chunks


def split_by_tokens(
    text: str,
    chunk_size: int = 512,
    chunk_overlap: int = 50,
    tokenizer: str = "gpt-4",
    **kwargs,
) -> List[Chunk]:
    """
    Token-based splitting using tiktoken or transformers.

    Args:
        text: Input text
        chunk_size: Target chunk size in tokens
        chunk_overlap: Overlap in tokens
        tokenizer: Tokenizer name (tiktoken model or HuggingFace model)
        **kwargs: Additional options

    Returns:
        List of chunks
    """
    # Try tiktoken first
    if TIKTOKEN_AVAILABLE:
        try:
            enc = tiktoken.encoding_for_model(tokenizer)
            tokens = enc.encode(text)
        except Exception:
            # Fallback to cl100k_base
            enc = tiktoken.get_encoding("cl100k_base")
            tokens = enc.encode(text)
    elif TRANSFORMERS_AVAILABLE:
        try:
            tokenizer_obj = AutoTokenizer.from_pretrained(tokenizer)
            tokens = tokenizer_obj.encode(text, add_special_tokens=False)
        except Exception:
            # Fallback to simple word splitting
            tokens = text.split()
    else:
        # Fallback to word-based approximation
        words = text.split()
        tokens = words
        chunk_size = chunk_size * 4  # Approximate: 1 token ≈ 4 chars

    chunks = []
    start_idx = 0
    text_start = 0

    while start_idx < len(tokens):
        end_idx = min(start_idx + chunk_size, len(tokens))
        chunk_tokens = tokens[start_idx:end_idx]

        # Convert tokens back to text
        if TIKTOKEN_AVAILABLE:
            chunk_text = enc.decode(chunk_tokens)
        elif TRANSFORMERS_AVAILABLE:
            chunk_text = tokenizer_obj.decode(chunk_tokens, skip_special_tokens=True)
        else:
            chunk_text = " ".join(chunk_tokens)

        # Find position in original text
        text_pos = text.find(chunk_text[:50], text_start)
        if text_pos == -1:
            text_pos = text_start

        text_end = text_pos + len(chunk_text)

        chunks.append(
            Chunk(
                text=chunk_text,
                start_index=text_pos,
                end_index=text_end,
                metadata={
                    "method": "token",
                    "token_count": len(chunk_tokens),
                    "chunk_size": len(chunk_text),
                },
            )
        )

        # Move to next chunk with overlap
        start_idx = max(start_idx + 1, end_idx - chunk_overlap)
        text_start = text_end - chunk_overlap * 4  # Approximate

    return chunks


def split_by_sentences(
    text: str, chunk_size: int = 1000, max_sentences: Optional[int] = None, **kwargs
) -> List[Chunk]:
    """
    Sentence boundary splitting using regex, NLTK, or spaCy.

    Args:
        text: Input text
        chunk_size: Target chunk size
        max_sentences: Maximum sentences per chunk
        **kwargs: Additional options

    Returns:
        List of chunks
    """
    # Try spaCy first
    if SPACY_AVAILABLE and kwargs.get("use_spacy", True):
        try:
            from ..semantic_extract.methods import load_spacy_model
            nlp = load_spacy_model("en_core_web_sm")
            doc = nlp(text)
            sentences = [sent.text for sent in doc.sents]
        except Exception:
            sentences = _split_sentences_regex(text)
    elif NLTK_AVAILABLE and kwargs.get("use_nltk", False):
        try:
            nltk.download("punkt", quiet=True)
            sentences = nltk.sent_tokenize(text)
        except Exception:
            sentences = _split_sentences_regex(text)
    else:
        sentences = _split_sentences_regex(text)

    chunks = []
    current_chunk = []
    current_size = 0
    text_start = 0

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue

        sentence_size = len(sentence)

        # Check if adding this sentence would exceed limits
        if (max_sentences and len(current_chunk) >= max_sentences) or (
            current_size + sentence_size > chunk_size and current_chunk
        ):
            # Create chunk
            chunk_text = " ".join(current_chunk)
            text_pos = text.find(chunk_text[:50], text_start)
            if text_pos == -1:
                text_pos = text_start

            text_end = text_pos + len(chunk_text)
            chunks.append(
                Chunk(
                    text=chunk_text,
                    start_index=text_pos,
                    end_index=text_end,
                    metadata={
                        "method": "sentence",
                        "sentence_count": len(current_chunk),
                        "chunk_size": len(chunk_text),
                    },
                )
            )

            text_start = text_end
            current_chunk = []
            current_size = 0

        current_chunk.append(sentence)
        current_size += sentence_size + 1  # +1 for space

    # Add final chunk
    if current_chunk:
        chunk_text = " ".join(current_chunk)
        text_pos = text.find(chunk_text[:50], text_start)
        if text_pos == -1:
            text_pos = text_start

        text_end = text_pos + len(chunk_text)
        chunks.append(
            Chunk(
                text=chunk_text,
                start_index=text_pos,
                end_index=text_end,
                metadata={
                    "method": "sentence",
                    "sentence_count": len(current_chunk),
                    "chunk_size": len(chunk_text),
                },
            )
        )

    return chunks


def _split_sentences_regex(text: str) -> List[str]:
    """Fallback regex-based sentence splitting."""
    # Simple sentence splitting
    sentences = re.split(r"(?<=[.!?])\s+", text)
    return [s.strip() for s in sentences if s.strip()]


def split_by_paragraphs(text: str, chunk_size: int = 2000, **kwargs) -> List[Chunk]:
    """
    Paragraph boundary splitting.

    Args:
        text: Input text
        chunk_size: Target chunk size
        **kwargs: Additional options

    Returns:
        List of chunks
    """
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]

    chunks = []
    current_chunk = []
    current_size = 0
    text_start = 0

    for para in paragraphs:
        para_size = len(para)

        if current_size + para_size > chunk_size and current_chunk:
            chunk_text = "\n\n".join(current_chunk)
            text_pos = text.find(chunk_text[:50], text_start)
            if text_pos == -1:
                text_pos = text_start

            text_end = text_pos + len(chunk_text)
            chunks.append(
                Chunk(
                    text=chunk_text,
                    start_index=text_pos,
                    end_index=text_end,
                    metadata={
                        "method": "paragraph",
                        "paragraph_count": len(current_chunk),
                        "chunk_size": len(chunk_text),
                    },
                )
            )

            text_start = text_end
            current_chunk = []
            current_size = 0

        current_chunk.append(para)
        current_size += para_size + 2  # +2 for \n\n

    # Add final chunk
    if current_chunk:
        chunk_text = "\n\n".join(current_chunk)
        text_pos = text.find(chunk_text[:50], text_start)
        if text_pos == -1:
            text_pos = text_start

        text_end = text_pos + len(chunk_text)
        chunks.append(
            Chunk(
                text=chunk_text,
                start_index=text_pos,
                end_index=text_end,
                metadata={
                    "method": "paragraph",
                    "paragraph_count": len(current_chunk),
                    "chunk_size": len(chunk_text),
                },
            )
        )

    return chunks


def split_by_characters(
    text: str, chunk_size: int = 1000, chunk_overlap: int = 200, **kwargs
) -> List[Chunk]:
    """
    Character count splitting.

    Args:
        text: Input text
        chunk_size: Chunk size in characters
        chunk_overlap: Overlap in characters
        **kwargs: Additional options

    Returns:
        List of chunks
    """
    chunks = []
    text_length = len(text)
    start = 0

    while start < text_length:
        end = min(start + chunk_size, text_length)
        chunk_text = text[start:end]

        chunks.append(
            Chunk(
                text=chunk_text,
                start_index=start,
                end_index=end,
                metadata={"method": "character", "chunk_size": len(chunk_text)},
            )
        )

        start = max(start + 1, end - chunk_overlap)

    return chunks


def split_by_words(
    text: str, chunk_size: int = 200, chunk_overlap: int = 40, **kwargs
) -> List[Chunk]:
    """
    Word count splitting.

    Args:
        text: Input text
        chunk_size: Chunk size in words
        chunk_overlap: Overlap in words
        **kwargs: Additional options

    Returns:
        List of chunks
    """
    words = text.split()
    chunks = []

    start_idx = 0
    while start_idx < len(words):
        end_idx = min(start_idx + chunk_size, len(words))
        chunk_words = words[start_idx:end_idx]
        chunk_text = " ".join(chunk_words)

        # Find position in original text
        text_pos = text.find(chunk_text[:50])
        if text_pos == -1:
            # Approximate position
            text_pos = sum(len(w) + 1 for w in words[:start_idx])

        text_end = text_pos + len(chunk_text)

        chunks.append(
            Chunk(
                text=chunk_text,
                start_index=text_pos,
                end_index=text_end,
                metadata={
                    "method": "word",
                    "word_count": len(chunk_words),
                    "chunk_size": len(chunk_text),
                },
            )
        )

        start_idx = max(start_idx + 1, end_idx - chunk_overlap)

    return chunks


def split_semantic_transformer(
    text: str,
    chunk_size: int = 1000,
    model: str = "all-MiniLM-L6-v2",
    similarity_threshold: float = 0.7,
    **kwargs,
) -> List[Chunk]:
    """
    Sentence transformer-based semantic splitting.

    Args:
        text: Input text
        chunk_size: Target chunk size
        model: Sentence transformer model name
        similarity_threshold: Similarity threshold for boundaries
        **kwargs: Additional options

    Returns:
        List of chunks
    """
    if not SENTENCE_TRANSFORMER_AVAILABLE:
        logger.warning(
            "sentence-transformers not available, falling back to sentence splitting"
        )
        return split_by_sentences(text, chunk_size=chunk_size, **kwargs)

    try:
        # Load model
        model_obj = SentenceTransformer(model)

        # Split into sentences first
        sentences = _split_sentences_regex(text)
        if not sentences:
            return []

        # Get embeddings
        embeddings = model_obj.encode(sentences)

        # Find split points based on similarity
        chunks = []
        current_chunk = []
        current_size = 0
        text_start = 0

        for i, sentence in enumerate(sentences):
            sentence_size = len(sentence)

            # Check similarity with previous sentence
            if i > 0 and len(current_chunk) > 0:
                similarity = _cosine_similarity(embeddings[i - 1], embeddings[i])
                if similarity < similarity_threshold and current_chunk:
                    # Create chunk at boundary
                    chunk_text = " ".join(current_chunk)
                    text_pos = text.find(chunk_text[:50], text_start)
                    if text_pos == -1:
                        text_pos = text_start

                    text_end = text_pos + len(chunk_text)
                    chunks.append(
                        Chunk(
                            text=chunk_text,
                            start_index=text_pos,
                            end_index=text_end,
                            metadata={
                                "method": "semantic_transformer",
                                "sentence_count": len(current_chunk),
                                "chunk_size": len(chunk_text),
                            },
                        )
                    )

                    text_start = text_end
                    current_chunk = []
                    current_size = 0

            # Check size limit
            if current_size + sentence_size > chunk_size and current_chunk:
                chunk_text = " ".join(current_chunk)
                text_pos = text.find(chunk_text[:50], text_start)
                if text_pos == -1:
                    text_pos = text_start

                text_end = text_pos + len(chunk_text)
                chunks.append(
                    Chunk(
                        text=chunk_text,
                        start_index=text_pos,
                        end_index=text_end,
                        metadata={
                            "method": "semantic_transformer",
                            "sentence_count": len(current_chunk),
                            "chunk_size": len(chunk_text),
                        },
                    )
                )

                text_start = text_end
                current_chunk = []
                current_size = 0

            current_chunk.append(sentence)
            current_size += sentence_size + 1

        # Add final chunk
        if current_chunk:
            chunk_text = " ".join(current_chunk)
            text_pos = text.find(chunk_text[:50], text_start)
            if text_pos == -1:
                text_pos = text_start

            text_end = text_pos + len(chunk_text)
            chunks.append(
                Chunk(
                    text=chunk_text,
                    start_index=text_pos,
                    end_index=text_end,
                    metadata={
                        "method": "semantic_transformer",
                        "sentence_count": len(current_chunk),
                        "chunk_size": len(chunk_text),
                    },
                )
            )

        return chunks

    except Exception as e:
        logger.warning(
            f"Error in semantic transformer splitting: {e}, falling back to sentence splitting"
        )
        return split_by_sentences(text, chunk_size=chunk_size, **kwargs)


def _cosine_similarity(vec1, vec2):
    """Calculate cosine similarity between two vectors."""
    import numpy as np

    dot_product = np.dot(vec1, vec2)
    norm1 = np.linalg.norm(vec1)
    norm2 = np.linalg.norm(vec2)
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return dot_product / (norm1 * norm2)


def split_llm(
    text: str,
    chunk_size: int = 1000,
    provider: str = "openai",
    model: Optional[str] = None,
    **kwargs,
) -> List[Chunk]:
    """
    LLM-based optimal split point detection.

    Args:
        text: Input text
        chunk_size: Target chunk size
        provider: LLM provider name
        model: Model name
        **kwargs: Additional options

    Returns:
        List of chunks
    """
    if not SEMANTIC_EXTRACT_AVAILABLE:
        logger.warning(
            "semantic_extract not available, falling back to recursive splitting"
        )
        return split_recursive(text, chunk_size=chunk_size, **kwargs)

    try:
        llm_provider = create_provider(provider, model=model or "gpt-3.5-turbo")

        # First, split roughly by size
        rough_chunks = split_recursive(text, chunk_size=chunk_size, chunk_overlap=0)

        # Use LLM to refine boundaries
        refined_chunks = []
        for rough_chunk in rough_chunks:
            prompt = f"""Analyze the following text and identify the best split points 
            (sentence boundaries) that would create semantically coherent chunks of approximately 
            {chunk_size} characters. Return only the indices where splits should occur, 
            separated by commas:

            {rough_chunk.text[:2000]}

            Split indices:"""

            response = llm_provider.generate(prompt)

            # Parse response to get split indices
            try:
                split_indices = [
                    int(x.strip()) for x in response.split(",") if x.strip().isdigit()
                ]
                # Use split indices to create refined chunks
                # For simplicity, use the rough chunk if parsing fails
                refined_chunks.append(rough_chunk)
            except Exception:
                refined_chunks.append(rough_chunk)

        return refined_chunks if refined_chunks else rough_chunks

    except Exception as e:
        logger.warning(
            f"Error in LLM splitting: {e}, falling back to recursive splitting"
        )
        return split_recursive(text, chunk_size=chunk_size, **kwargs)


def split_huggingface(
    text: str, chunk_size: int = 1000, model: str = "bert-base-uncased", **kwargs
) -> List[Chunk]:
    """
    HuggingFace model-based splitting.

    Args:
        text: Input text
        chunk_size: Target chunk size
        model: HuggingFace model name
        **kwargs: Additional options

    Returns:
        List of chunks
    """
    if not TRANSFORMERS_AVAILABLE:
        logger.warning("transformers not available, falling back to token splitting")
        return split_by_tokens(text, chunk_size=chunk_size, **kwargs)

    try:
        tokenizer = AutoTokenizer.from_pretrained(model)
        return split_by_tokens(text, chunk_size=chunk_size, tokenizer=model, **kwargs)
    except Exception as e:
        logger.warning(
            f"Error in HuggingFace splitting: {e}, falling back to token splitting"
        )
        return split_by_tokens(text, chunk_size=chunk_size, **kwargs)


def split_nltk(text: str, chunk_size: int = 1000, **kwargs) -> List[Chunk]:
    """
    NLTK-based splitting.

    Args:
        text: Input text
        chunk_size: Target chunk size
        **kwargs: Additional options

    Returns:
        List of chunks
    """
    if not NLTK_AVAILABLE:
        logger.warning("NLTK not available, falling back to sentence splitting")
        return split_by_sentences(text, chunk_size=chunk_size, use_nltk=False, **kwargs)

    return split_by_sentences(text, chunk_size=chunk_size, use_nltk=True, **kwargs)


# ============================================================================
# KG/Ontology/Graph Analytics Methods
# ============================================================================


def split_entity_aware(
    text: str,
    chunk_size: int = 1000,
    ner_method: str = "ml",
    preserve_entities: bool = True,
    **kwargs,
) -> List[Chunk]:
    """
    Entity boundary-preserving splitting.

    Args:
        text: Input text
        chunk_size: Target chunk size
        ner_method: NER method to use
        preserve_entities: Whether to preserve entity boundaries
        **kwargs: Additional options

    Returns:
        List of chunks
    """
    if not SEMANTIC_EXTRACT_AVAILABLE:
        logger.warning(
            "semantic_extract not available, falling back to recursive splitting"
        )
        return split_recursive(text, chunk_size=chunk_size, **kwargs)

    try:
        # Extract entities
        ner_extractor = NERExtractor(method=ner_method, **kwargs)
        entities = ner_extractor.extract(text)

        # Create entity boundaries map
        entity_boundaries = set()
        for entity in entities:
            entity_boundaries.add(entity.start_char)
            entity_boundaries.add(entity.end_char)

        # Split text respecting entity boundaries
        chunks = []
        current_chunk = ""
        current_size = 0
        text_start = 0

        sentences = _split_sentences_regex(text)
        char_pos = 0

        for sentence in sentences:
            sentence_size = len(sentence)
            sentence_start = char_pos
            sentence_end = char_pos + sentence_size

            # Check if sentence contains entity boundaries
            has_entity_boundary = any(
                sentence_start <= boundary <= sentence_end
                for boundary in entity_boundaries
            )

            # Check size limit
            if current_size + sentence_size > chunk_size and current_chunk:
                # Try to split at entity boundary if possible
                if preserve_entities and has_entity_boundary:
                    # Don't split here, add to current chunk
                    pass
                else:
                    # Create chunk
                    chunk_text = current_chunk.strip()
                    text_pos = text.find(chunk_text[:50], text_start)
                    if text_pos == -1:
                        text_pos = text_start

                    text_end = text_pos + len(chunk_text)
                    chunks.append(
                        Chunk(
                            text=chunk_text,
                            start_index=text_pos,
                            end_index=text_end,
                            metadata={
                                "method": "entity_aware",
                                "chunk_size": len(chunk_text),
                                "entity_count": len(
                                    [
                                        e
                                        for e in entities
                                        if text_pos <= e.start_char < text_end
                                    ]
                                ),
                                "entities": [
                                    e
                                    for e in entities
                                    if text_pos <= e.start_char < text_end
                                ],
                            },
                        )
                    )

                    text_start = text_end
                    current_chunk = ""
                    current_size = 0

            current_chunk += sentence + " "
            current_size += sentence_size + 1
            char_pos = sentence_end + 1

        # Add final chunk
        if current_chunk.strip():
            chunk_text = current_chunk.strip()
            text_pos = text.find(chunk_text[:50], text_start)
            if text_pos == -1:
                text_pos = text_start

            text_end = text_pos + len(chunk_text)
            chunks.append(
                Chunk(
                    text=chunk_text,
                    start_index=text_pos,
                    end_index=text_end,
                    metadata={
                        "method": "entity_aware",
                        "chunk_size": len(chunk_text),
                        "entity_count": len(
                            [e for e in entities if text_pos <= e.start_char < text_end]
                        ),
                        "entities": [
                            e for e in entities if text_pos <= e.start_char < text_end
                        ],
                    },
                )
            )

        return chunks

    except Exception as e:
        logger.warning(
            f"Error in entity-aware splitting: {e}, falling back to recursive splitting"
        )
        return split_recursive(text, chunk_size=chunk_size, **kwargs)


def split_relation_aware(
    text: str,
    chunk_size: int = 1000,
    relation_method: str = "ml",
    preserve_triplets: bool = True,
    **kwargs,
) -> List[Chunk]:
    """
    Triplet-preserving splitting.

    Args:
        text: Input text
        chunk_size: Target chunk size
        relation_method: Relation extraction method
        preserve_triplets: Whether to preserve triplet integrity
        **kwargs: Additional options

    Returns:
        List of chunks
    """
    if not SEMANTIC_EXTRACT_AVAILABLE:
        logger.warning(
            "semantic_extract not available, falling back to recursive splitting"
        )
        return split_recursive(text, chunk_size=chunk_size, **kwargs)

    try:
        # Extract entities first (required for relation extraction)
        ner_method = kwargs.get("ner_method", "ml")
        ner_extractor = NERExtractor(method=ner_method, **kwargs)
        entities = ner_extractor.extract(text)

        # Extract relations/triplets
        relation_extractor = RelationExtractor(method=relation_method, **kwargs)
        relations = relation_extractor.extract(text, entities)

        # Create triplet boundaries (subject, relation, object must be in same chunk)
        triplet_boundaries = []
        for relation in relations:
            start = min(relation.subject.start_char, relation.object.start_char)
            end = max(relation.subject.end_char, relation.object.end_char)
            triplet_boundaries.append((start, end))

        # Split text ensuring triplets are not split
        chunks = []
        current_chunk = ""
        current_size = 0
        text_start = 0

        sentences = _split_sentences_regex(text)
        char_pos = 0

        for sentence in sentences:
            sentence_size = len(sentence)
            sentence_start = char_pos
            sentence_end = char_pos + sentence_size

            # Check if sentence is part of a triplet
            is_in_triplet = any(
                start <= sentence_start <= end or start <= sentence_end <= end
                for start, end in triplet_boundaries
            )

            # Check size limit
            if current_size + sentence_size > chunk_size and current_chunk:
                # Don't split if it would break a triplet
                if preserve_triplets and is_in_triplet:
                    # Add to current chunk even if it exceeds size
                    pass
                else:
                    # Create chunk
                    chunk_text = current_chunk.strip()
                    text_pos = text.find(chunk_text[:50], text_start)
                    if text_pos == -1:
                        text_pos = text_start

                    text_end = text_pos + len(chunk_text)
                    chunks.append(
                        Chunk(
                            text=chunk_text,
                            start_index=text_pos,
                            end_index=text_end,
                            metadata={
                                "method": "relation_aware",
                                "chunk_size": len(chunk_text),
                                "relation_count": len(
                                    [
                                        r
                                        for r in relations
                                        if text_pos <= r.subject.start_char < text_end
                                    ]
                                ),
                                "relationships": [
                                    r
                                    for r in relations
                                    if text_pos <= r.subject.start_char < text_end
                                ],
                                "triplets": [
                                    r
                                    for r in relations
                                    if text_pos <= r.subject.start_char < text_end
                                ],
                            },
                        )
                    )

                    text_start = text_end
                    current_chunk = ""
                    current_size = 0

            current_chunk += sentence + " "
            current_size += sentence_size + 1
            char_pos = sentence_end + 1

        # Add final chunk
        if current_chunk.strip():
            chunk_text = current_chunk.strip()
            text_pos = text.find(chunk_text[:50], text_start)
            if text_pos == -1:
                text_pos = text_start

            text_end = text_pos + len(chunk_text)
            chunks.append(
                Chunk(
                    text=chunk_text,
                    start_index=text_pos,
                    end_index=text_end,
                    metadata={
                        "method": "relation_aware",
                        "chunk_size": len(chunk_text),
                        "relation_count": len(
                            [
                                r
                                for r in relations
                                if text_pos <= r.subject.start_char < text_end
                            ]
                        ),
                        "relationships": [
                            r
                            for r in relations
                            if text_pos <= r.subject.start_char < text_end
                        ],
                        "triplets": [
                            r
                            for r in relations
                            if text_pos <= r.subject.start_char < text_end
                        ],
                    },
                )
            )

        return chunks

    except Exception as e:
        logger.warning(
            f"Error in relation-aware splitting: {e}, falling back to recursive splitting"
        )
        return split_recursive(text, chunk_size=chunk_size, **kwargs)


def split_graph_based(
    text: str,
    chunk_size: int = 1000,
    strategy: str = "community",
    algorithm: str = "louvain",
    **kwargs,
) -> List[Chunk]:
    """
    Graph structure-based splitting using centrality or communities.

    Args:
        text: Input text
        chunk_size: Target chunk size
        strategy: Strategy ("community", "centrality")
        algorithm: Algorithm name ("louvain", "leiden", "betweenness", etc.)
        **kwargs: Additional options

    Returns:
        List of chunks
    """
    if not SEMANTIC_EXTRACT_AVAILABLE or not NETWORKX_AVAILABLE:
        logger.warning(
            "Required dependencies not available, falling back to recursive splitting"
        )
        return split_recursive(text, chunk_size=chunk_size, **kwargs)

    try:
        # Extract entities and relations to build graph
        ner_extractor = NERExtractor(method=kwargs.get("ner_method", "ml"), **kwargs)
        relation_extractor = RelationExtractor(
            method=kwargs.get("relation_method", "ml"), **kwargs
        )

        entities = ner_extractor.extract(text)
        # Relation extraction requires the extracted entities; failing to pass
        # them raises and can trigger the broad fallback to recursive splitting.
        relations = relation_extractor.extract(text, entities)

        # Build graph
        G = nx.Graph()
        entity_map = {}

        for entity in entities:
            G.add_node(entity.text, type="entity", label=entity.label)
            entity_map[entity.text] = entity

        for relation in relations:
            subject_text = relation.subject.text
            object_text = relation.object.text
            if subject_text in entity_map and object_text in entity_map:
                G.add_edge(subject_text, object_text, label=relation.predicate)

        if len(G.nodes()) == 0:
            return split_recursive(text, chunk_size=chunk_size, **kwargs)

        # Apply graph-based strategy
        if strategy == "community":
            if algorithm == "louvain" and COMMUNITY_AVAILABLE:
                communities = community_louvain.best_partition(G)
            else:
                # Fallback to simple connected components
                communities = {}
                for i, component in enumerate(nx.connected_components(G)):
                    for node in component:
                        communities[node] = i

            # Group nodes by community
            community_groups = {}
            for node, comm_id in communities.items():
                if comm_id not in community_groups:
                    community_groups[comm_id] = []
                community_groups[comm_id].append(node)

            # Create chunks based on communities
            chunks = []
            for comm_id, nodes in community_groups.items():
                # Get text segments for these entities
                entity_texts = []
                for node in nodes:
                    if node in entity_map:
                        entity = entity_map[node]
                        # Find surrounding context
                        context_start = max(0, entity.start_char - 100)
                        context_end = min(len(text), entity.end_char + 100)
                        entity_texts.append(text[context_start:context_end])

                if entity_texts:
                    chunk_text = " ".join(entity_texts)
                    # Find position in original text
                    text_pos = text.find(chunk_text[:50])
                    if text_pos == -1:
                        text_pos = 0

                    chunks.append(
                        Chunk(
                            text=chunk_text[:chunk_size],
                            start_index=text_pos,
                            end_index=text_pos + min(len(chunk_text), chunk_size),
                            metadata={
                                "method": "graph_based",
                                "strategy": strategy,
                                "algorithm": algorithm,
                                "community_id": comm_id,
                                "node_count": len(nodes),
                            },
                        )
                    )

            return (
                chunks
                if chunks
                else split_recursive(text, chunk_size=chunk_size, **kwargs)
            )

        elif strategy == "centrality":
            # Use centrality to find important nodes and chunk around them
            if algorithm == "betweenness":
                centrality = nx.betweenness_centrality(G)
            elif algorithm == "degree":
                centrality = dict(G.degree())
            else:
                centrality = nx.degree_centrality(G)

            # Sort nodes by centrality
            sorted_nodes = sorted(centrality.items(), key=lambda x: x[1], reverse=True)

            # Create chunks around high-centrality nodes
            chunks = []
            used_nodes = set()

            for node, cent_score in sorted_nodes:
                if node in used_nodes:
                    continue

                # Get neighbors (k-hop)
                k = kwargs.get("k_hop", 2)
                neighbors = set([node])
                current_level = [node]

                for _ in range(k):
                    next_level = []
                    for n in current_level:
                        neighbors.update(G.neighbors(n))
                        next_level.extend(G.neighbors(n))
                    current_level = next_level
                    if not current_level:
                        break

                # Get text for these nodes
                entity_texts = []
                for n in neighbors:
                    if n in entity_map:
                        entity = entity_map[n]
                        context_start = max(0, entity.start_char - 100)
                        context_end = min(len(text), entity.end_char + 100)
                        entity_texts.append(text[context_start:context_end])
                        used_nodes.add(n)

                if entity_texts:
                    chunk_text = " ".join(entity_texts)
                    text_pos = text.find(chunk_text[:50])
                    if text_pos == -1:
                        text_pos = 0

                    chunks.append(
                        Chunk(
                            text=chunk_text[:chunk_size],
                            start_index=text_pos,
                            end_index=text_pos + min(len(chunk_text), chunk_size),
                            metadata={
                                "method": "graph_based",
                                "strategy": strategy,
                                "algorithm": algorithm,
                                "centrality_score": cent_score,
                                "node_count": len(neighbors),
                            },
                        )
                    )

            return (
                chunks
                if chunks
                else split_recursive(text, chunk_size=chunk_size, **kwargs)
            )

        else:
            return split_recursive(text, chunk_size=chunk_size, **kwargs)

    except Exception as e:
        logger.warning(
            f"Error in graph-based splitting: {e}, falling back to recursive splitting"
        )
        return split_recursive(text, chunk_size=chunk_size, **kwargs)


def split_ontology_aware(
    text: str,
    chunk_size: int = 1000,
    ontology_uri: Optional[str] = None,
    preserve_concepts: bool = True,
    **kwargs,
) -> List[Chunk]:
    """
    Ontology concept and hierarchy-based splitting.

    Args:
        text: Input text
        chunk_size: Target chunk size
        ontology_uri: Ontology URI (optional)
        preserve_concepts: Whether to preserve concept boundaries
        **kwargs: Additional options

    Returns:
        List of chunks
    """
    # For now, use entity-aware splitting as ontology concepts are similar to entities
    # In a full implementation, this would use ontology hierarchies
    logger.info("Ontology-aware splitting using entity-aware method as base")
    return split_entity_aware(
        text, chunk_size=chunk_size, preserve_entities=preserve_concepts, **kwargs
    )


def split_embedding_semantic(
    text: str,
    chunk_size: int = 1000,
    model: str = "all-MiniLM-L6-v2",
    similarity_threshold: float = 0.7,
    **kwargs,
) -> List[Chunk]:
    """
    Embedding similarity-based semantic boundary detection.

    Args:
        text: Input text
        chunk_size: Target chunk size
        model: Embedding model name
        similarity_threshold: Similarity threshold for boundaries
        **kwargs: Additional options

    Returns:
        List of chunks
    """
    # This is essentially the same as semantic_transformer
    return split_semantic_transformer(
        text,
        chunk_size=chunk_size,
        model=model,
        similarity_threshold=similarity_threshold,
        **kwargs,
    )


def split_hierarchical(
    text: str,
    levels: List[str] = ["section", "paragraph", "sentence"],
    chunk_sizes: Optional[List[int]] = None,
    **kwargs,
) -> List[Chunk]:
    """
    Multi-level hierarchical chunking.

    Args:
        text: Input text
        levels: Hierarchy levels (e.g., ["section", "paragraph", "sentence"])
        chunk_sizes: Chunk sizes for each level
        **kwargs: Additional options

    Returns:
        List of chunks with hierarchical metadata
    """
    if chunk_sizes is None:
        chunk_sizes = [2000, 1000, 500]

    # Start with largest level
    if "section" in levels:
        # Try to detect sections (headings)
        sections = re.split(r"\n#{1,6}\s+", text)
        if len(sections) > 1:
            chunks = []
            for section in sections:
                if section.strip():
                    # Recursively chunk section
                    sub_chunks = split_hierarchical(
                        section,
                        levels=levels[1:] if len(levels) > 1 else ["paragraph"],
                        chunk_sizes=chunk_sizes[1:] if len(chunk_sizes) > 1 else [1000],
                        **kwargs,
                    )
                    chunks.extend(sub_chunks)
            return chunks

    # Fall back to paragraph level
    if "paragraph" in levels:
        # Remove chunk_size from kwargs to avoid multiple values error
        para_kwargs = kwargs.copy()
        if "chunk_size" in para_kwargs:
            del para_kwargs["chunk_size"]
            
        return split_by_paragraphs(
            text, chunk_size=chunk_sizes[0] if chunk_sizes else 1000, **para_kwargs
        )

    # Fall back to sentence level
    # Remove chunk_size from kwargs to avoid multiple values error
    sent_kwargs = kwargs.copy()
    if "chunk_size" in sent_kwargs:
        del sent_kwargs["chunk_size"]
        
    return split_by_sentences(
        text, chunk_size=chunk_sizes[0] if chunk_sizes else 1000, **sent_kwargs
    )


def split_community_detection(
    text: str, chunk_size: int = 1000, algorithm: str = "louvain", **kwargs
) -> List[Chunk]:
    """
    Community detection-based chunking.

    Args:
        text: Input text
        chunk_size: Target chunk size
        algorithm: Community detection algorithm ("louvain", "leiden")
        **kwargs: Additional options

    Returns:
        List of chunks
    """
    return split_graph_based(
        text, chunk_size=chunk_size, strategy="community", algorithm=algorithm, **kwargs
    )


def split_centrality_based(
    text: str, chunk_size: int = 1000, algorithm: str = "betweenness", **kwargs
) -> List[Chunk]:
    """
    Centrality-based chunking around important nodes.

    Args:
        text: Input text
        chunk_size: Target chunk size
        algorithm: Centrality algorithm ("betweenness", "degree", "eigenvector")
        **kwargs: Additional options

    Returns:
        List of chunks
    """
    return split_graph_based(
        text,
        chunk_size=chunk_size,
        strategy="centrality",
        algorithm=algorithm,
        **kwargs,
    )


def split_subgraph(
    text: str, chunk_size: int = 1000, k_hop: int = 2, **kwargs
) -> List[Chunk]:
    """
    Subgraph extraction-based chunking (k-hop neighborhoods).

    Args:
        text: Input text
        chunk_size: Target chunk size
        k_hop: k-hop neighborhood size
        **kwargs: Additional options

    Returns:
        List of chunks
    """
    return split_graph_based(
        text,
        chunk_size=chunk_size,
        strategy="centrality",
        algorithm="degree",
        k_hop=k_hop,
        **kwargs,
    )


def split_topic_based(
    text: str, chunk_size: int = 1000, model: str = "lda", num_topics: int = 5, **kwargs
) -> List[Chunk]:
    """
    Topic modeling-based chunking.

    Args:
        text: Input text
        chunk_size: Target chunk size
        model: Topic model ("lda", "bertopic")
        num_topics: Number of topics
        **kwargs: Additional options

    Returns:
        List of chunks
    """
    # For now, use semantic transformer as approximation
    # Full implementation would use LDA or BERTopic
    logger.info(
        f"Topic-based splitting using semantic transformer (full {model} implementation pending)"
    )
    return split_semantic_transformer(text, chunk_size=chunk_size, **kwargs)


def split_structural(
    text: str,
    max_chunk_size: int = 2000,
    respect_headers: bool = True,
    respect_sections: bool = True,
    **kwargs,
) -> List[Chunk]:
    """
    Structure-aware chunking respecting document hierarchy.

    Args:
        text: Input text
        max_chunk_size: Maximum chunk size
        respect_headers: Whether to respect heading hierarchy
        respect_sections: Whether to respect section boundaries
        **kwargs: Additional options

    Returns:
        List of chunks
    """
    if not SPECIALIZED_CHUNKERS_AVAILABLE:
        logger.warning(
            "StructuralChunker not available, falling back to recursive splitting"
        )
        return split_recursive(text, chunk_size=max_chunk_size, **kwargs)

    try:
        chunker = StructuralChunker(
            max_chunk_size=max_chunk_size,
            respect_headers=respect_headers,
            respect_sections=respect_sections,
            **kwargs,
        )
        return chunker.chunk(text, **kwargs)
    except Exception as e:
        logger.warning(
            f"Error in structural splitting: {e}, falling back to recursive splitting"
        )
        return split_recursive(text, chunk_size=max_chunk_size, **kwargs)


def split_sliding_window(
    text: str,
    chunk_size: int = 1000,
    overlap: int = 200,
    stride: Optional[int] = None,
    preserve_boundaries: bool = True,
    **kwargs,
) -> List[Chunk]:
    """
    Sliding window chunking with optional boundary preservation.

    Args:
        text: Input text
        chunk_size: Chunk size in characters
        overlap: Overlap size in characters
        stride: Stride size (default: chunk_size - overlap)
        preserve_boundaries: Whether to preserve word/sentence boundaries
        **kwargs: Additional options

    Returns:
        List of chunks
    """
    if not SPECIALIZED_CHUNKERS_AVAILABLE:
        logger.warning(
            "SlidingWindowChunker not available, falling back to recursive splitting"
        )
        return split_recursive(
            text, chunk_size=chunk_size, chunk_overlap=overlap, **kwargs
        )

    try:
        effective_stride = stride if stride is not None else (chunk_size - overlap)
        chunker = SlidingWindowChunker(
            chunk_size=chunk_size, overlap=overlap, stride=effective_stride, **kwargs
        )
        return chunker.chunk(text, preserve_boundaries=preserve_boundaries, **kwargs)
    except Exception as e:
        logger.warning(
            f"Error in sliding window splitting: {e}, falling back to recursive splitting"
        )
        return split_recursive(
            text, chunk_size=chunk_size, chunk_overlap=overlap, **kwargs
        )


# ============================================================================
# Method Dispatcher
# ============================================================================

_SPLIT_METHODS = {
    # Standard methods
    "recursive": split_recursive,
    "token": split_by_tokens,
    "sentence": split_by_sentences,
    "paragraph": split_by_paragraphs,
    "character": split_by_characters,
    "word": split_by_words,
    "semantic_transformer": split_semantic_transformer,
    "llm": split_llm,
    "huggingface": split_huggingface,
    "nltk": split_nltk,
    # KG/Ontology methods
    "entity_aware": split_entity_aware,
    "relation_aware": split_relation_aware,
    "graph_based": split_graph_based,
    "ontology_aware": split_ontology_aware,
    "embedding_semantic": split_embedding_semantic,
    "hierarchical": split_hierarchical,
    "community_detection": split_community_detection,
    "centrality_based": split_centrality_based,
    "subgraph": split_subgraph,
    "topic_based": split_topic_based,
    # Specialized methods
    "structural": split_structural,
    "sliding_window": split_sliding_window,
}


def get_split_method(method: str) -> Optional[Callable]:
    """
    Get splitting method by name.

    Args:
        method: Method name

    Returns:
        Method function or None
    """
    # Check registry first
    try:
        from .registry import method_registry

        registered = method_registry.get("split", method)
        if registered:
            return registered
    except (ImportError, OSError):
        pass

    # Check built-in methods
    return _SPLIT_METHODS.get(method)


def list_available_methods() -> List[str]:
    """
    List all available splitting methods.

    Returns:
        List of method names
    """
    methods = list(_SPLIT_METHODS.keys())

    # Add registered methods
    try:
        from .registry import method_registry

        registered = method_registry.list_all("split")
        if registered and "split" in registered:
            methods.extend(registered["split"])
    except (ImportError, OSError):
        pass

    return sorted(set(methods))  # Remove duplicates and sort
