"""
Sliding Window Chunker Module

This module provides fixed-size chunking with overlap capabilities using
a sliding window approach, with optional boundary preservation for better
text coherence.

Key Features:
    - Fixed-size sliding window chunking
    - Configurable overlap and stride
    - Boundary preservation (word/sentence)
    - Fixed-size or boundary-aware modes
    - Chunk metadata tracking

Main Classes:
    - SlidingWindowChunker: Main sliding window chunking coordinator

Example Usage:
    >>> from semantica.split import SlidingWindowChunker
    >>> chunker = SlidingWindowChunker(chunk_size=1000, overlap=200)
    >>> chunks = chunker.chunk(text, preserve_boundaries=True)
    >>> overlap_chunks = chunker.chunk_with_overlap(text, overlap_size=300)

Author: Semantica Contributors
License: MIT
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..utils.exceptions import ProcessingError, ValidationError
from ..utils.logging import get_logger
from ..utils.progress_tracker import get_progress_tracker
from .semantic_chunker import Chunk


class SlidingWindowChunker:
    """Sliding window chunker with overlap."""

    def __init__(self, **config):
        """
        Initialize sliding window chunker.

        Args:
            **config: Configuration options:
                - chunk_size: Chunk size in characters
                - overlap: Overlap size in characters (default: 0)
                - stride: Stride size (default: chunk_size - overlap)
        """
        self.logger = get_logger("sliding_window_chunker")
        self.config = config
        self.progress_tracker = get_progress_tracker()
        # Ensure progress tracker is enabled
        if not self.progress_tracker.enabled:
            self.progress_tracker.enabled = True

        self.chunk_size = config.get("chunk_size", 1000)
        self.overlap = config.get("overlap", 0)
        self.stride = config.get("stride", self.chunk_size - self.overlap)

        if self.chunk_size <= 0:
            raise ValidationError("chunk_size must be positive")
        if self.overlap < 0:
            raise ValidationError("overlap must be non-negative")
        if self.overlap >= self.chunk_size:
            raise ValidationError("overlap must be less than chunk_size")
        if self.stride <= 0:
            raise ValidationError("stride must be positive")

    def chunk(self, text: str, **options) -> List[Chunk]:
        """
        Split text using sliding window approach.

        Args:
            text: Input text to chunk
            **options: Chunking options:
                - preserve_boundaries: Try to preserve word/sentence boundaries (default: True)

        Returns:
            list: List of chunks
        """
        tracking_id = self.progress_tracker.start_tracking(
            module="split",
            submodule="SlidingWindowChunker",
            message="Splitting text using sliding window",
        )

        try:
            if not text:
                self.progress_tracker.stop_tracking(
                    tracking_id, status="completed", message="No text provided"
                )
                return []

            preserve_boundaries = options.get("preserve_boundaries", True)

            if preserve_boundaries:
                self.progress_tracker.update_tracking(
                    tracking_id, message="Chunking with boundary preservation..."
                )
                chunks = self._chunk_with_boundaries(text)
            else:
                self.progress_tracker.update_tracking(
                    tracking_id, message="Chunking with fixed-size windows..."
                )
                chunks = self._chunk_fixed_size(text)

            self.progress_tracker.stop_tracking(
                tracking_id, status="completed", message=f"Created {len(chunks)} chunks"
            )
            return chunks

        except Exception as e:
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message=str(e)
            )
            raise

    def _chunk_fixed_size(self, text: str) -> List[Chunk]:
        """Chunk text with fixed-size windows."""
        chunks = []
        text_length = len(text)

        start = 0
        chunk_index = 0

        while start < text_length:
            end = min(start + self.chunk_size, text_length)
            chunk_text = text[start:end]

            chunks.append(
                Chunk(
                    text=chunk_text,
                    start_index=start,
                    end_index=end,
                    metadata={
                        "chunk_index": chunk_index,
                        "chunk_size": len(chunk_text),
                        "has_overlap": chunk_index > 0,
                    },
                )
            )

            start += self.stride
            chunk_index += 1

        return chunks

    def _chunk_with_boundaries(self, text: str) -> List[Chunk]:
        """Chunk text preserving word/sentence boundaries."""
        chunks = []
        text_length = len(text)

        start = 0
        chunk_index = 0

        while start < text_length:
            # Determine end position
            end_pos = min(start + self.chunk_size, text_length)

            # If not at end, try to find a good boundary
            if end_pos < text_length:
                # Look for sentence boundary (., !, ?)
                boundary_chars = [".", "!", "?", "\n"]
                for boundary in boundary_chars:
                    last_boundary = text.rfind(boundary, start, end_pos)
                    if (
                        last_boundary > start + self.chunk_size * 0.5
                    ):  # At least 50% of target size
                        end_pos = last_boundary + 1
                        break

                # If no sentence boundary, look for word boundary
                if end_pos == min(start + self.chunk_size, text_length):
                    last_space = text.rfind(" ", start, end_pos)
                    if last_space > start + self.chunk_size * 0.5:
                        end_pos = last_space

            chunk_text = text[start:end_pos].strip()

            if chunk_text:
                chunks.append(
                    Chunk(
                        text=chunk_text,
                        start_index=start,
                        end_index=end_pos,
                        metadata={
                            "chunk_index": chunk_index,
                            "chunk_size": len(chunk_text),
                            "has_overlap": chunk_index > 0,
                            "boundary_preserved": end_pos < text_length,
                        },
                    )
                )

            # Move to next chunk with stride
            start += self.stride

            # Ensure we don't go backwards
            if start <= end_pos - self.overlap:
                start = end_pos - self.overlap

            chunk_index += 1

        return chunks

    def chunk_with_overlap(
        self, text: str, overlap_size: Optional[int] = None
    ) -> List[Chunk]:
        """
        Chunk text with specified overlap.

        Args:
            text: Input text
            overlap_size: Overlap size (uses default if None)

        Returns:
            list: List of chunks
        """
        if overlap_size is None:
            return self.chunk(text)
        if overlap_size < 0:
            raise ValidationError("overlap_size must be non-negative")
        if overlap_size >= self.chunk_size:
            raise ValidationError("overlap_size must be less than chunk_size")

        original_overlap = self.overlap
        original_stride = self.stride

        try:
            self.overlap = overlap_size
            self.stride = self.chunk_size - self.overlap
            return self.chunk(text)
        finally:
            self.overlap = original_overlap
            self.stride = original_stride
