"""
Semantic Chunker Module

This module provides meaning-based document splitting using spaCy and other
NLP libraries for optimal semantic boundaries, preserving sentence and
paragraph coherence.

Key Features:
    - Semantic boundary detection using NLP
    - Sentence-aware chunking
    - Paragraph preservation
    - Configurable chunk size and overlap
    - spaCy integration with fallback
    - Metadata tracking (sentence count, token count)

Main Classes:
    - SemanticChunker: Main semantic chunking coordinator
    - Chunk: Chunk representation dataclass

Example Usage:
    >>> from semantica.split import SemanticChunker
    >>> chunker = SemanticChunker(chunk_size=1000, chunk_overlap=200)
    >>> chunks = chunker.chunk(text)
    >>> sentence_chunks = chunker.chunk_by_sentences(text, max_sentences=5)

Author: Semantica Contributors
License: MIT
"""

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from ..utils.exceptions import ProcessingError
from ..utils.helpers import safe_import
from ..utils.logging import get_logger
from ..utils.progress_tracker import get_progress_tracker


_, SPACY_AVAILABLE = safe_import("spacy")


@dataclass
class Chunk:
    """Chunk representation."""
    text: str
    start_index: int
    end_index: int
    metadata: Dict[str, Any] = field(default_factory=dict)
    id: Optional[str] = None


class SemanticChunker:
    """Semantic chunker for meaning-based splitting."""

    def __init__(self, **config):
        """
        Initialize semantic chunker.

        Args:
            **config: Configuration options:
                - model: spaCy model name (default: "en_core_web_sm")
                - chunk_size: Target chunk size in characters
                - chunk_overlap: Overlap between chunks
                - language: Language code
        """
        self.logger = get_logger("semantic_chunker")
        self.config = config

        self.chunk_size = config.get("chunk_size", 1000)
        self.chunk_overlap = config.get("chunk_overlap", 200)
        self.language = config.get("language", "en")
        self.progress_tracker = get_progress_tracker()
        # Ensure progress tracker is enabled
        if not self.progress_tracker.enabled:
            self.progress_tracker.enabled = True

        # Initialize spaCy model if available
        self.nlp = None
        if SPACY_AVAILABLE:
            model_name = config.get("model", "en_core_web_sm")
            try:
                from ..semantic_extract.methods import load_spacy_model
                self.nlp = load_spacy_model(model_name)
            except OSError:
                self.logger.warning(
                    f"spaCy model {model_name} not found. Using fallback chunking."
                )
            except Exception:
                self.logger.warning(
                    "spaCy model %s failed to initialize and will be disabled "
                    "for this chunker instance. Using fallback chunking.",
                    model_name,
                    exc_info=True,
                )

    def chunk(self, text: str, **options) -> List[Chunk]:
        """
        Split text into semantic chunks.

        Args:
            text: Input text to chunk
            **options: Chunking options:
                - preserve_sentences: Preserve sentence boundaries (default: True)
                - preserve_paragraphs: Preserve paragraph boundaries (default: True)

        Returns:
            list: List of chunks
        """
        tracking_id = self.progress_tracker.start_tracking(
            module="split",
            submodule="SemanticChunker",
            message="Splitting text into semantic chunks",
        )

        try:
            if not text:
                self.progress_tracker.stop_tracking(
                    tracking_id, status="completed", message="No text provided"
                )
                return []

            # Use spaCy if available
            if self.nlp:
                self.progress_tracker.update_tracking(
                    tracking_id, message="Chunking with spaCy..."
                )
                chunks = self._chunk_with_spacy(text, **options)
            else:
                self.progress_tracker.update_tracking(
                    tracking_id, message="Chunking with fallback method..."
                )
                chunks = self._chunk_fallback(text, **options)

            self.progress_tracker.stop_tracking(
                tracking_id, status="completed", message=f"Created {len(chunks)} chunks"
            )
            return chunks

        except Exception as e:
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message=str(e)
            )
            raise

    def _chunk_with_spacy(self, text: str, **options) -> List[Chunk]:
        """Chunk text using spaCy."""
        chunks = []

        # Process text with spaCy
        doc = self.nlp(text)

        # Split by sentences first
        sentences = [sent.text for sent in doc.sents]

        current_chunk_text = ""
        current_start = 0
        chunk_start = 0

        for sentence in sentences:
            sentence_text = sentence.strip()
            if not sentence_text:
                continue

            # Check if adding this sentence would exceed chunk size
            potential_chunk = (
                current_chunk_text + " " + sentence_text
                if current_chunk_text
                else sentence_text
            )

            if len(potential_chunk) <= self.chunk_size or not current_chunk_text:
                # Add sentence to current chunk
                current_chunk_text = potential_chunk
                current_start += len(sentence_text) + 1
            else:
                # Save current chunk and start new one
                chunk_text = current_chunk_text.strip()
                if chunk_text:
                    # Find actual start position in original text
                    start_pos = text.find(chunk_text[:50], chunk_start)
                    end_pos = start_pos + len(chunk_text)

                    chunks.append(
                        Chunk(
                            text=chunk_text,
                            start_index=start_pos if start_pos >= 0 else chunk_start,
                            end_index=end_pos,
                            metadata={
                                "sentence_count": len(re.split(r"[.!?]+", chunk_text)),
                                "token_count": len(self.nlp(chunk_text)),
                            },
                        )
                    )

                # Start new chunk with overlap
                if self.chunk_overlap > 0:
                    # Include last part of previous chunk as overlap
                    overlap_text = current_chunk_text[-self.chunk_overlap :]
                    current_chunk_text = overlap_text + " " + sentence_text
                    chunk_start = text.find(overlap_text[:50], max(0, chunk_start))
                else:
                    current_chunk_text = sentence_text
                    chunk_start = text.find(sentence_text[:50], max(0, chunk_start))
                current_start = len(current_chunk_text)

        # Add final chunk
        if current_chunk_text.strip():
            start_pos = text.find(current_chunk_text[:50], chunk_start)
            end_pos = (
                start_pos + len(current_chunk_text.strip())
                if start_pos >= 0
                else len(text)
            )

            chunks.append(
                Chunk(
                    text=current_chunk_text.strip(),
                    start_index=start_pos if start_pos >= 0 else chunk_start,
                    end_index=end_pos,
                    metadata={
                        "sentence_count": len(re.split(r"[.!?]+", current_chunk_text)),
                        "token_count": len(self.nlp(current_chunk_text.strip())),
                    },
                )
            )

        return chunks

    def _chunk_fallback(self, text: str, **options) -> List[Chunk]:
        """Fallback chunking without spaCy."""
        chunks = []

        # Split by paragraphs first
        paragraphs = text.split("\n\n")

        current_chunk_text = ""
        chunk_start = 0

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            potential_chunk = (
                current_chunk_text + "\n\n" + para if current_chunk_text else para
            )

            if len(potential_chunk) <= self.chunk_size or not current_chunk_text:
                current_chunk_text = potential_chunk
            else:
                # Save current chunk
                chunk_text = current_chunk_text.strip()
                if chunk_text:
                    start_pos = text.find(chunk_text[:50], chunk_start)
                    end_pos = (
                        start_pos + len(chunk_text)
                        if start_pos >= 0
                        else chunk_start + len(chunk_text)
                    )

                    chunks.append(
                        Chunk(
                            text=chunk_text,
                            start_index=start_pos if start_pos >= 0 else chunk_start,
                            end_index=end_pos,
                            metadata={
                                "paragraph_count": current_chunk_text.count("\n\n") + 1
                            },
                        )
                    )

                # Start new chunk with overlap
                if self.chunk_overlap > 0:
                    overlap_text = current_chunk_text[-self.chunk_overlap :]
                    current_chunk_text = overlap_text + "\n\n" + para
                    chunk_start = text.find(overlap_text[:50], max(0, chunk_start))
                else:
                    current_chunk_text = para
                    chunk_start = text.find(para[:50], max(0, chunk_start))

        # Add final chunk
        if current_chunk_text.strip():
            start_pos = text.find(current_chunk_text[:50], chunk_start)
            end_pos = (
                start_pos + len(current_chunk_text.strip())
                if start_pos >= 0
                else len(text)
            )

            chunks.append(
                Chunk(
                    text=current_chunk_text.strip(),
                    start_index=start_pos if start_pos >= 0 else chunk_start,
                    end_index=end_pos,
                    metadata={"paragraph_count": current_chunk_text.count("\n\n") + 1},
                )
            )

        return chunks

    def chunk_by_sentences(self, text: str, max_sentences: int = 5) -> List[Chunk]:
        """
        Chunk text by sentence boundaries.

        Args:
            text: Input text
            max_sentences: Maximum sentences per chunk

        Returns:
            list: List of chunks
        """
        # Split sentences using regex
        sentences = re.split(r"(?<=[.!?])\s+", text)

        chunks = []
        current_chunk = []
        chunk_start = 0

        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue

            current_chunk.append(sentence)

            if len(current_chunk) >= max_sentences:
                chunk_text = " ".join(current_chunk)
                start_pos = text.find(chunk_text[:50], chunk_start)
                end_pos = (
                    start_pos + len(chunk_text)
                    if start_pos >= 0
                    else chunk_start + len(chunk_text)
                )

                chunks.append(
                    Chunk(
                        text=chunk_text,
                        start_index=start_pos if start_pos >= 0 else chunk_start,
                        end_index=end_pos,
                        metadata={"sentence_count": len(current_chunk)},
                    )
                )

                chunk_start = end_pos
                current_chunk = []

        # Add remaining sentences
        if current_chunk:
            chunk_text = " ".join(current_chunk)
            start_pos = text.find(chunk_text[:50], chunk_start)
            end_pos = start_pos + len(chunk_text) if start_pos >= 0 else len(text)

            chunks.append(
                Chunk(
                    text=chunk_text,
                    start_index=start_pos if start_pos >= 0 else chunk_start,
                    end_index=end_pos,
                    metadata={"sentence_count": len(current_chunk)},
                )
            )

        return chunks
