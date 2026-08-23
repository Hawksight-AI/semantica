"""
Embedding Methods Module

This module provides all embedding methods as simple, reusable functions for
embedding generation, optimization, similarity calculation, and pooling.
It supports multiple embedding approaches and integrates with the method registry
for extensibility.

Supported Methods:

Embedding Generation:
    - "default": Default embedding generation using EmbeddingGenerator
    - "text": Text embedding generation

Text Embedding:
    - "sentence_transformers": Sentence-transformers model-based embedding
    - "fastembed": FastEmbed model-based embedding (fast and efficient)
    - "fallback": Hash-based fallback embedding

Pooling Strategies:
    - "mean": Mean pooling
    - "max": Max pooling
    - "cls": CLS token pooling
    - "attention": Attention-based pooling
    - "hierarchical": Hierarchical pooling

Similarity Calculation:
    - "cosine": Cosine similarity
    - "euclidean": Euclidean similarity

Algorithms Used:

Embedding Generation:
    - Sentence-transformers Encoding: Transformer-based sentence embedding generation using pre-trained models
    - FastEmbed Encoding: Fast and efficient embedding generation using FastEmbed library
    - Hash-based Fallback Embeddings: SHA-256 hash-based deterministic embeddings (128-dimensional)
    - Batch Processing: Vectorized processing for multiple items simultaneously

Similarity Calculation:
    - Cosine Similarity: Dot product divided by vector norms for normalized similarity (0-1 range)
    - Euclidean Similarity: L2 norm distance converted to similarity score (0-1 range)

Pooling Strategies:
    - Mean Pooling: Arithmetic mean across embedding dimension
    - Max Pooling: Element-wise maximum across embedding dimension
    - CLS Token Pooling: First token/embedding extraction (for transformer models)
    - Attention-based Pooling: Softmax-weighted sum using dot product attention scores
    - Hierarchical Pooling: Two-level pooling (chunk-level then global-level mean pooling)

Key Features:
    - Multiple embedding generation methods
    - Multiple optimization methods
    - Multiple pooling strategies
    - Multiple similarity calculation methods
    - Method dispatchers with registry support
    - Custom method registration capability
    - Consistent interface across all methods

Main Functions:
    - generate_embeddings: Embedding generation wrapper
    - embed_text: Text embedding wrapper
    - calculate_similarity: Similarity calculation wrapper
    - pool_embeddings: Pooling strategy wrapper
    - get_embedding_method: Get embedding method by name
    - list_available_methods: List registered methods

Example Usage:
    >>> from semantica.embeddings.methods import embed_text, calculate_similarity
    >>> text_emb1 = embed_text("Hello world", method="sentence_transformers")
    >>> text_emb2 = embed_text("Hi there", method="fastembed")
    >>> similarity = calculate_similarity(text_emb1, text_emb2, method="cosine")
    >>> from semantica.embeddings.methods import get_embedding_method
    >>> method = get_embedding_method("text", "custom_method")
"""

from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

import numpy as np

from ..utils.exceptions import ConfigurationError, ProcessingError
from ..utils.logging import get_logger
from ..utils.custom_methods import CUSTOM_METHOD_FELL_BACK, call_custom_method
from .config import embeddings_config
from .embedding_generator import EmbeddingGenerator
from .pooling_strategies import PoolingStrategyFactory
from .registry import method_registry
from .text_embedder import TextEmbedder

logger = get_logger("embeddings_methods")


def generate_embeddings(
    data: Union[str, Path, List[Union[str, Path]]],
    data_type: Optional[str] = None,
    method: str = "default",
    **kwargs,
) -> np.ndarray:
    """
    Generate embeddings from data (convenience function).

    This is a user-friendly wrapper that generates embeddings using the specified method.

    Args:
        data: Input data - can be text string, file path, or list of texts/paths
        data_type: Data type - "text" (auto-detected if None)
        method: Generation method (default: "default")
            - "default": Use EmbeddingGenerator with auto-detection
            - "text": Text embedding generation
        **kwargs: Additional options passed to embedder

    Returns:
        np.ndarray: Generated embeddings (1D for single item, 2D for batch)

    Examples:
        >>> from semantica.embeddings.methods import generate_embeddings
        >>> emb = generate_embeddings("Hello world", method="default")
        >>> embs = generate_embeddings(["text1", "text2"], method="text")
    """
    # Check for custom method in registry, skip self-reference
    custom_method = method_registry.get("generation", method)
    if custom_method and custom_method is not generate_embeddings:
        fallback = kwargs.pop("fallback_on_custom_error", False)
        result = call_custom_method(
            logger, method, custom_method, data, data_type=data_type, fallback_on_custom_error=fallback, **kwargs
        )
        if result is not CUSTOM_METHOD_FELL_BACK:
            return result

    try:
        if method == "default":
            generator = EmbeddingGenerator(**kwargs)
            return generator.generate_embeddings(data, data_type=data_type, **kwargs)
        elif method == "text":
            return embed_text(data, **kwargs)
        else:
            raise ProcessingError(f"Unknown generation method: {method}")

    except Exception as e:
        logger.error(f"Failed to generate embeddings: {e}")
        raise


def embed_text(
    text: Union[str, List[str]], method: str = "sentence_transformers", **kwargs
) -> np.ndarray:
    """
    Generate text embeddings (convenience function).

    This is a user-friendly wrapper that generates text embeddings using the specified method.

    Args:
        text: Input text string or list of texts
        method: Text embedding method (default: "sentence_transformers")
            - "sentence_transformers": Sentence-transformers model-based embedding
            - "fastembed": FastEmbed model-based embedding (fast and efficient)
            - "fallback": Hash-based fallback embedding
        **kwargs: Additional options passed to TextEmbedder

    Returns:
        np.ndarray: Text embeddings (1D for single text, 2D for batch)

    Examples:
        >>> from semantica.embeddings.methods import embed_text
        >>> emb = embed_text("Hello world", method="sentence_transformers")
        >>> embs = embed_text(["text1", "text2"], method="sentence_transformers")
    """
    # Check for custom method in registry, skip self-reference
    custom_method = method_registry.get("text", method)
    if custom_method and custom_method is not embed_text:
        fallback = kwargs.pop("fallback_on_custom_error", False)
        result = call_custom_method(
            logger, method, custom_method, text, fallback_on_custom_error=fallback, **kwargs
        )
        if result is not CUSTOM_METHOD_FELL_BACK:
            return result

    try:
        # Get config
        config = embeddings_config.get_method_config("text")
        config.update(kwargs)

        # Set method if specified
        if method == "fastembed":
            config["method"] = "fastembed"
            # Use FastEmbed default model if not specified
            if "model_name" not in config:
                config["model_name"] = "BAAI/bge-small-en-v1.5"
        elif method == "sentence_transformers":
            config["method"] = "sentence_transformers"

        embedder = TextEmbedder(**config)

        if isinstance(text, list):
            return embedder.embed_batch(text, **kwargs)
        else:
            return embedder.embed_text(text, **kwargs)

    except Exception as e:
        logger.error(f"Failed to embed text: {e}")
        raise


def calculate_similarity(
    embedding1: np.ndarray, embedding2: np.ndarray, method: str = "cosine", **kwargs
) -> float:
    """
    Calculate similarity between embeddings (convenience function).

    This is a user-friendly wrapper that calculates similarity using the specified method.

    Args:
        embedding1: First embedding vector
        embedding2: Second embedding vector
        method: Similarity method (default: "cosine")
            - "cosine": Cosine similarity (dot product / norms)
            - "euclidean": Euclidean similarity (converted to 0-1 range)
        **kwargs: Additional options (unused)

    Returns:
        float: Similarity score (0-1 range)

    Examples:
        >>> from semantica.embeddings.methods import calculate_similarity
        >>> similarity = calculate_similarity(emb1, emb2, method="cosine")
        >>> print(f"Similarity: {similarity:.3f}")
    """
    # Check for custom method in registry, skip self-reference
    custom_method = method_registry.get("similarity", method)
    if custom_method and custom_method is not calculate_similarity:
        fallback = kwargs.pop("fallback_on_custom_error", False)
        result = call_custom_method(
            logger, method, custom_method, embedding1, embedding2, fallback_on_custom_error=fallback, **kwargs
        )
        if result is not CUSTOM_METHOD_FELL_BACK:
            return result

    try:
        generator = EmbeddingGenerator(**kwargs)
        return generator.compare_embeddings(
            embedding1, embedding2, method=method, **kwargs
        )

    except Exception as e:
        logger.error(f"Failed to calculate similarity: {e}")
        raise


def pool_embeddings(
    embeddings: np.ndarray, method: str = "mean", **kwargs
) -> np.ndarray:
    """
    Pool embeddings (convenience function).

    This is a user-friendly wrapper that pools embeddings using the specified strategy.

    Args:
        embeddings: Input embeddings array (n_embeddings, dim)
        method: Pooling strategy (default: "mean")
            - "mean": Mean pooling
            - "max": Max pooling
            - "cls": CLS token pooling
            - "attention": Attention-based pooling
            - "hierarchical": Hierarchical pooling
        **kwargs: Additional options passed to pooling strategy

    Returns:
        np.ndarray: Pooled embedding vector (dim,)

    Examples:
        >>> from semantica.embeddings.methods import pool_embeddings
        >>> pooled = pool_embeddings(embeddings, method="mean")
        >>> attention_pooled = pool_embeddings(embeddings, method="attention")
    """
    # Check for custom method in registry, skip self-reference
    custom_method = method_registry.get("pooling", method)
    if custom_method and custom_method is not pool_embeddings:
        fallback = kwargs.pop("fallback_on_custom_error", False)
        result = call_custom_method(
            logger, method, custom_method, embeddings, fallback_on_custom_error=fallback, **kwargs
        )
        if result is not CUSTOM_METHOD_FELL_BACK:
            return result

    try:
        strategy = PoolingStrategyFactory.create(method, **kwargs)
        return strategy.pool(embeddings, **kwargs)

    except Exception as e:
        logger.error(f"Failed to pool embeddings: {e}")
        raise


def get_embedding_method(task: str, name: str) -> Optional[Callable]:
    """
    Get a registered embedding method.

    Args:
        task: Task type ("generation", "text", "image", "pooling", "provider", "similarity")
        name: Method name

    Returns:
        Registered method or None if not found

    Examples:
        >>> from semantica.embeddings.methods import get_embedding_method
        >>> method = get_embedding_method("text", "custom_method")
        >>> if method:
        ...     result = method("Hello world")
    """
    return method_registry.get(task, name)


def list_available_methods(task: Optional[str] = None) -> Dict[str, List[str]]:
    """
    List all available embedding methods.

    Args:
        task: Optional task type filter

    Returns:
        Dictionary mapping task types to method names

    Examples:
        >>> from semantica.embeddings.methods import list_available_methods
        >>> all_methods = list_available_methods()
        >>> text_methods = list_available_methods("text")
    """
    return method_registry.list_all(task)


def check_available_providers() -> Dict[str, bool]:
    """
    Check which embedding providers are available in the environment.

    Returns:
        dict: Dictionary mapping provider names to availability status

    Example:
        >>> from semantica.embeddings.methods import check_available_providers
        >>> providers = check_available_providers()
        >>> if providers["sentence_transformers"]:
        ...     print("Sentence Transformers is available")
        >>> if providers["fastembed"]:
        ...     print("FastEmbed is available")
    """
    providers = {}

    # Check sentence-transformers
    try:
        import sentence_transformers
        providers["sentence_transformers"] = True
    except (ImportError, OSError):
        providers["sentence_transformers"] = False

    # Check FastEmbed
    try:
        import fastembed
        providers["fastembed"] = True
    except (ImportError, OSError):
        providers["fastembed"] = False

    # Check OpenAI
    try:
        import openai
        providers["openai"] = True
    except (ImportError, OSError):
        providers["openai"] = False

    return providers


# Register default methods
method_registry.register("generation", "default", generate_embeddings)
method_registry.register("generation", "text", generate_embeddings)
method_registry.register("text", "sentence_transformers", embed_text)
method_registry.register("text", "fastembed", embed_text)
method_registry.register("text", "fallback", embed_text)
method_registry.register("similarity", "cosine", calculate_similarity)
method_registry.register("similarity", "euclidean", calculate_similarity)
method_registry.register("pooling", "mean", pool_embeddings)
method_registry.register("pooling", "max", pool_embeddings)
method_registry.register("pooling", "cls", pool_embeddings)
method_registry.register("pooling", "attention", pool_embeddings)
method_registry.register("pooling", "hierarchical", pool_embeddings)
