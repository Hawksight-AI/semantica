"""
FAISS Store Module

This module provides FAISS (Facebook AI Similarity Search) integration for vector
storage and similarity search in the Semantica framework, supporting various index
types (flat, IVF, HNSW, PQ) and distance metrics for efficient vector operations.

Key Features:
    - Multiple index types (Flat, IVF, HNSW, Product Quantization)
    - Distance metrics (L2, Inner Product)
    - Index persistence (save/load)
    - Batch vector operations
    - Index optimization and training
    - Optional dependency handling

Main Classes:
    - FAISSStore: Main FAISS store for vector operations
    - FAISSIndex: FAISS index wrapper with metadata support
    - FAISSSearch: FAISS search operations
    - FAISSIndexBuilder: FAISS index construction and configuration

Example Usage:
    >>> from semantica.vector_store import FAISSStore
    >>> store = FAISSStore(dimension=768)
    >>> index = store.create_index(index_type="flat", metric="L2")
    >>> vector_ids = store.add_vectors(vectors, ids, metadata)
    >>> results = store.search_similar(query_vector, k=10)
    >>> store.save_index("index.faiss")
    >>> 
    >>> from semantica.vector_store import FAISSIndexBuilder
    >>> builder = FAISSIndexBuilder(dimension=768)
    >>> index = builder.build_index(index_type="ivf", metric="L2", nlist=100)

Author: Semantica Contributors
License: MIT
"""

import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np

from ..utils.exceptions import ProcessingError, ValidationError
from ..utils.logging import get_logger
from ..utils.progress_tracker import get_progress_tracker

# Optional FAISS import
try:
    import faiss

    FAISS_AVAILABLE = True
except (ImportError, OSError):
    FAISS_AVAILABLE = False
    faiss = None


class FAISSIndex:
    """FAISS index wrapper."""

    _STATE_SUFFIX = ".metadata.json"
    _STATE_VERSION = 1

    def __init__(self, index: Any, dimension: int, index_type: str = "flat"):
        """Initialize FAISS index wrapper."""
        self.index = index
        self.dimension = dimension
        self.index_type = index_type
        self.vector_ids: List[str] = []
        self.metadata: Dict[str, Dict[str, Any]] = {}

    def add_vectors(self, vectors: np.ndarray, ids: Optional[List[str]] = None):
        """
        Add vectors to index.

        Skips any id already present in vector_ids rather than appending a
        second physical vector under the same id. FAISS indices here don't
        support removing or replacing a single vector in place, so an
        "update" isn't possible; without this check, re-running an add for
        ids that already exist (e.g. retrying an interrupted migration)
        would silently duplicate vectors under the same id on every retry.
        """
        if ids is None:
            ids = [f"vec_{i}" for i in range(len(vectors))]

        new_rows = []
        new_ids = []
        existing = set(self.vector_ids)
        for row, vec_id in zip(vectors, ids):
            if vec_id in existing:
                continue
            new_rows.append(row)
            new_ids.append(vec_id)
            existing.add(vec_id)

        if new_rows:
            self.index.add(np.array(new_rows, dtype=np.float32))
            self.vector_ids.extend(new_ids)

    def search(
        self, query_vectors: np.ndarray, k: int = 10
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Search for similar vectors."""
        return self.index.search(query_vectors.astype(np.float32), k)

    def get_vector(self, vector_id: str) -> Optional[np.ndarray]:
        """Get vector by ID."""
        if vector_id not in self.vector_ids:
            return None

        idx = self.vector_ids.index(vector_id)
        reconstruct = getattr(self.index, "reconstruct", None)
        if not callable(reconstruct):
            return None

        try:
            return np.asarray(reconstruct(idx), dtype=np.float32)
        except NotImplementedError:
            return None
        except RuntimeError as exc:
            message = str(exc).casefold()
            unsupported_errors = (
                "reconstruct not implemented",
                "reconstruct_from_offset not implemented",
            )
            if any(error in message for error in unsupported_errors):
                return None
            if "direct map not initialized" in message:
                # IVF-family indices (e.g. IndexIVFFlat) support exact reconstruction
                # but need their DirectMap built once before reconstruct() works.
                make_direct_map = getattr(self.index, "make_direct_map", None)
                if not callable(make_direct_map):
                    return None
                make_direct_map()
                return np.asarray(reconstruct(idx), dtype=np.float32)
            raise

    def get_metadata(self, vector_id: str) -> Optional[Dict[str, Any]]:
        """Get metadata by ID."""
        return self.metadata.get(vector_id)

    def save(self, path: Union[str, Path]):
        """Save the FAISS index and its logical IDs and metadata to disk."""
        if not FAISS_AVAILABLE:
            raise ProcessingError("FAISS not available")

        path = Path(path)
        state = {
            "version": self._STATE_VERSION,
            "vector_ids": list(self.vector_ids),
            "metadata": dict(self.metadata),
        }
        self._validate_logical_state(state, self.index.ntotal, self._state_path(path))
        try:
            json.dumps(state, ensure_ascii=False, indent=2)
        except (TypeError, ValueError) as exc:
            raise ProcessingError("FAISS metadata must be JSON serializable") from exc

        state_path = self._state_path(path)
        staged_index = None
        staged_state = None
        backup_state = None
        backup_created = False
        state_installed = False
        preserve_backup = False

        try:
            staged_index = self._temporary_path(path)
            staged_state = self._temporary_path(state_path)
            faiss.write_index(self.index, str(staged_index))

            state["index_sha256"] = self._file_sha256(staged_index)
            serialized_state = json.dumps(state, ensure_ascii=False, indent=2)
            staged_state.write_text(f"{serialized_state}\n", encoding="utf-8")

            if state_path.exists():
                backup_state = self._temporary_path(state_path)
                shutil.copyfile(state_path, backup_state)
                backup_created = True

            os.replace(staged_state, state_path)
            state_installed = True
            os.replace(staged_index, path)
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            rollback_error = None
            try:
                if backup_created:
                    os.replace(backup_state, state_path)
                    backup_created = False
                elif state_installed:
                    state_path.unlink(missing_ok=True)
            except OSError as restore_exc:
                rollback_error = restore_exc
                preserve_backup = backup_created

            message = f"Failed to save FAISS index to {path}: {exc}"
            if rollback_error is not None:
                if backup_state is not None:
                    message += (
                        "; metadata rollback failed; recovery copy remains at "
                        f"{backup_state}: {rollback_error}"
                    )
                else:
                    message += f"; metadata rollback failed: {rollback_error}"
            raise ProcessingError(message) from exc
        finally:
            for temporary_path in (staged_index, staged_state, backup_state):
                if temporary_path is None:
                    continue
                if preserve_backup and temporary_path == backup_state:
                    continue
                try:
                    temporary_path.unlink(missing_ok=True)
                except OSError:
                    pass

    @classmethod
    def load(cls, path: Union[str, Path], dimension: int, index_type: str = "flat"):
        """Load an index and restore its logical state when present."""
        if not FAISS_AVAILABLE:
            raise ProcessingError("FAISS not available")

        path = Path(path)
        index = faiss.read_index(str(path))
        loaded = cls(index, dimension, index_type)
        state_path = cls._state_path(path)
        if not state_path.exists():
            return loaded

        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ProcessingError(
                f"Failed to load FAISS metadata from {state_path}: {exc}"
            ) from exc

        if not isinstance(state, dict):
            raise ProcessingError(f"Invalid FAISS metadata state: {state_path}")

        if state.get("version") != cls._STATE_VERSION:
            raise ProcessingError(f"Unsupported FAISS metadata version in {state_path}")

        cls._validate_logical_state(state, index.ntotal, state_path)
        expected_checksum = state.get("index_sha256")
        if not isinstance(expected_checksum, str) or len(expected_checksum) != 64:
            raise ProcessingError(f"Invalid FAISS index checksum in {state_path}")
        try:
            int(expected_checksum, 16)
        except ValueError as exc:
            raise ProcessingError(
                f"Invalid FAISS index checksum in {state_path}"
            ) from exc
        if cls._file_sha256(path) != expected_checksum.casefold():
            raise ProcessingError(
                "FAISS index checksum does not match its metadata state: "
                f"{state_path}"
            )

        loaded.vector_ids = state["vector_ids"]
        loaded.metadata = state["metadata"]
        return loaded

    @classmethod
    def _validate_logical_state(
        cls, state: Dict[str, Any], index_total: int, state_path: Path
    ) -> None:
        """Validate the logical ID and metadata state paired with an index."""
        vector_ids = state.get("vector_ids")
        metadata = state.get("metadata")
        if not isinstance(vector_ids, list) or not all(
            isinstance(vector_id, str) for vector_id in vector_ids
        ):
            raise ProcessingError(f"Invalid vector_ids in FAISS metadata: {state_path}")
        if len(vector_ids) != index_total:
            raise ProcessingError(
                "FAISS metadata vector count does not match the index: "
                f"{len(vector_ids)} != {index_total}"
            )
        if len(set(vector_ids)) != len(vector_ids):
            raise ProcessingError(
                f"Duplicate vector_ids in FAISS metadata: {state_path}"
            )
        if not isinstance(metadata, dict) or not all(
            isinstance(vector_id, str) and isinstance(value, dict)
            for vector_id, value in metadata.items()
        ):
            raise ProcessingError(f"Invalid metadata in FAISS state: {state_path}")
        unknown_metadata_ids = set(metadata).difference(vector_ids)
        if unknown_metadata_ids:
            raise ProcessingError(
                "FAISS metadata contains IDs not present in vector_ids: "
                f"{state_path}"
            )

    @staticmethod
    def _temporary_path(target: Path) -> Path:
        """Create a same-directory staging path suitable for atomic replacement."""
        descriptor, temporary_name = tempfile.mkstemp(
            dir=target.parent,
            prefix=f".{target.name}.",
            suffix=".tmp",
        )
        os.close(descriptor)
        return Path(temporary_name)

    @staticmethod
    def _file_sha256(path: Path) -> str:
        """Return the SHA-256 digest for a persisted FAISS index."""
        digest = hashlib.sha256()
        with path.open("rb") as file_handle:
            for chunk in iter(lambda: file_handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @classmethod
    def _state_path(cls, path: Union[str, Path]) -> Path:
        """Return the JSON sidecar path for a FAISS index file."""
        return Path(f"{path}{cls._STATE_SUFFIX}")


class FAISSSearch:
    """FAISS search operations."""

    def __init__(self, index: FAISSIndex):
        """Initialize FAISS search."""
        self.index = index
        self.logger = get_logger("faiss_search")

    def search_similar(
        self, query_vector: np.ndarray, k: int = 10, **options
    ) -> List[Dict[str, Any]]:
        """
        Search for similar vectors.

        Args:
            query_vector: Query vector
            k: Number of results
            **options: Search options

        Returns:
            List of search results
        """
        if query_vector.ndim == 1:
            query_vector = query_vector.reshape(1, -1)

        distances, indices = self.index.search(query_vector, k)

        results = []
        for i, (dist, idx) in enumerate(zip(distances[0], indices[0])):
            if idx < len(self.index.vector_ids):
                vector_id = self.index.vector_ids[idx]
                dist_val = float(dist)
                
                # Standardize score as similarity (0.0 to 1.0)
                # while preserving original distance
                similarity_score = 1.0 / (1.0 + max(0.0, dist_val))
                
                results.append(
                    {
                        "id": vector_id,
                        "score": similarity_score,
                        "distance": dist_val,
                        "metadata": self.index.metadata.get(vector_id, {}),
                        "vector": None,
                    }
                )

        return results


class FAISSIndexBuilder:
    """FAISS index builder."""

    def __init__(self, dimension: int = 768):
        """Initialize FAISS index builder."""
        self.dimension = dimension
        self.logger = get_logger("faiss_builder")

    def build_index(
        self, index_type: str = "flat", metric: str = "L2", **options
    ) -> FAISSIndex:
        """
        Build FAISS index.

        Args:
            index_type: Index type ("flat", "ivf", "hnsw", "pq")
            metric: Distance metric ("L2", "inner_product")
            **options: Index options

        Returns:
            FAISSIndex instance
        """
        if not FAISS_AVAILABLE:
            raise ProcessingError(
                "FAISS is not available. Install it with: pip install faiss-cpu or faiss-gpu"
            )

        # Create index based on type
        if index_type == "flat":
            if metric == "L2":
                index = faiss.IndexFlatL2(self.dimension)
            else:
                index = faiss.IndexFlatIP(self.dimension)

        elif index_type == "ivf":
            nlist = options.get("nlist", 100)
            quantizer = faiss.IndexFlatL2(self.dimension)
            index = faiss.IndexIVFFlat(quantizer, self.dimension, nlist)

        elif index_type == "hnsw":
            M = options.get("M", 32)
            index = faiss.IndexHNSWFlat(self.dimension, M)

        elif index_type == "pq":
            m = options.get("m", 8)  # Number of subquantizers
            bits = options.get("bits", 8)
            index = faiss.IndexPQ(self.dimension, m, bits)

        else:
            raise ValidationError(f"Unsupported index type: {index_type}")

        return FAISSIndex(index, self.dimension, index_type)

    def train_index(self, index: FAISSIndex, training_vectors: np.ndarray):
        """Train index on sample vectors."""
        if not isinstance(index.index, faiss.IndexIVFFlat):
            return  # Only IVF indices need training

        index.index.train(training_vectors.astype(np.float32))


class FAISSStore:
    """
    FAISS store for vector storage and similarity search.

    • FAISS index creation and management
    • Vector storage and retrieval
    • Similarity search and filtering
    • Index optimization and training
    • Performance optimization
    • Error handling and recovery
    """

    def __init__(self, dimension: int = 768, **config):
        """Initialize FAISS store."""
        self.logger = get_logger("faiss_store")
        self.config = config
        self.progress_tracker = get_progress_tracker()
        # Ensure progress tracker is enabled
        if not self.progress_tracker.enabled:
            self.progress_tracker.enabled = True
        self.dimension = dimension

        self.index: Optional[FAISSIndex] = None
        self.index_builder = FAISSIndexBuilder(dimension)
        self.search_engine: Optional[FAISSSearch] = None

        # Check FAISS availability
        if not FAISS_AVAILABLE:
            self.logger.warning(
                "FAISS not available. Install with: pip install faiss-cpu or faiss-gpu"
            )

    def create_index(
        self, index_type: str = "flat", metric: str = "L2", **options
    ) -> FAISSIndex:
        """
        Create FAISS index.

        Args:
            index_type: Index type ("flat", "ivf", "hnsw", "pq")
            metric: Distance metric ("L2", "inner_product")
            **options: Index options

        Returns:
            FAISSIndex instance
        """
        self.index = self.index_builder.build_index(index_type, metric, **options)
        self.search_engine = FAISSSearch(self.index)

        self.logger.info(f"Created FAISS index: {index_type} with metric {metric}")
        return self.index

    def add_vectors(
        self,
        vectors: Union[List[np.ndarray], np.ndarray],
        ids: Optional[List[str]] = None,
        metadata: Optional[List[Dict[str, Any]]] = None,
        **options,
    ) -> List[str]:
        """
        Add vectors to index.

        Any id that already exists in the index is skipped rather than
        stored as a second physical vector under the same id (see
        FAISSIndex.add_vectors), so calling this again with ids from a
        previous call is safe and doesn't accumulate duplicates. Metadata
        for those ids is still updated.

        Args:
            vectors: List of vectors or numpy array
            ids: Vector IDs
            metadata: Vector metadata
            **options: Additional options

        Returns:
            List of vector IDs (including ids that were already present
            and therefore not re-added as new vectors)
        """
        num_vectors = len(vectors) if isinstance(vectors, (list, np.ndarray)) else 1
        tracking_id = self.progress_tracker.start_tracking(
            module="vector_store",
            submodule="FAISSStore",
            message=f"Adding {num_vectors} vectors to FAISS index",
        )

        try:
            if self.index is None:
                self.progress_tracker.update_tracking(
                    tracking_id, message="Creating FAISS index..."
                )
                self.create_index(**options)

            # Convert to numpy array
            self.progress_tracker.update_tracking(
                tracking_id, message="Preparing vectors..."
            )
            if isinstance(vectors, list):
                vectors = np.array(vectors)

            vectors = vectors.astype(np.float32)

            # Generate IDs if not provided
            if ids is None:
                ids = [
                    f"vec_{len(self.index.vector_ids) + i}" for i in range(len(vectors))
                ]

            # Store metadata
            if metadata:
                self.progress_tracker.update_tracking(
                    tracking_id, message="Storing metadata..."
                )
                for vec_id, meta in zip(ids, metadata):
                    self.index.metadata[vec_id] = meta

            # Add vectors to index
            self.progress_tracker.update_tracking(
                tracking_id, message="Adding vectors to index..."
            )
            self.index.add_vectors(vectors, ids)

            self.logger.info(f"Added {len(vectors)} vectors to FAISS index")
            self.progress_tracker.stop_tracking(
                tracking_id,
                status="completed",
                message=f"Added {len(vectors)} vectors to FAISS index",
            )
            return ids
        except Exception as e:
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message=str(e)
            )
            raise

    def search_similar(
        self, query_vector: np.ndarray, k: int = 10, **options
    ) -> List[Dict[str, Any]]:
        """
        Search for similar vectors.

        Args:
            query_vector: Query vector
            k: Number of results
            **options: Search options

        Returns:
            List of search results
        """
        tracking_id = self.progress_tracker.start_tracking(
            module="vector_store",
            submodule="FAISSStore",
            message=f"Searching for {k} similar vectors",
        )

        try:
            if self.search_engine is None:
                self.progress_tracker.stop_tracking(
                    tracking_id, status="failed", message="Index not initialized"
                )
                raise ProcessingError(
                    "Index not initialized. Call create_index() first."
                )

            self.progress_tracker.update_tracking(
                tracking_id, message="Performing similarity search..."
            )
            results = self.search_engine.search_similar(query_vector, k, **options)

            self.progress_tracker.stop_tracking(
                tracking_id,
                status="completed",
                message=f"Found {len(results)} similar vectors",
            )
            return results
        except Exception as e:
            self.progress_tracker.stop_tracking(
                tracking_id, status="failed", message=str(e)
            )
            raise

    def save_index(self, path: Union[str, Path], **options) -> bool:
        """
        Save index to disk.

        Args:
            path: Path to save index
            **options: Save options

        Returns:
            True if successful

        Notes:
            Logical IDs and metadata are stored in ``<path>.metadata.json``.
            Keep the sidecar file with the FAISS index when moving it.
        """
        if self.index is None:
            raise ProcessingError("No index to save")

        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        self.index.save(path)
        self.logger.info(f"Saved FAISS index to {path}")
        return True

    def load_index(
        self, path: Union[str, Path], index_type: str = "flat", **options
    ) -> FAISSIndex:
        """
        Load index from disk.

        Args:
            path: Path to index file
            index_type: Index type
            **options: Load options

        Returns:
            FAISSIndex instance

        Notes:
            Restores logical IDs and metadata from ``<path>.metadata.json``
            when the sidecar is present. Legacy index files still load without it.
        """
        if not FAISS_AVAILABLE:
            raise ProcessingError("FAISS not available")

        self.index = FAISSIndex.load(path, self.dimension, index_type)
        self.search_engine = FAISSSearch(self.index)

        self.logger.info(f"Loaded FAISS index from {path}")
        return self.index

    def optimize_index(self, **options) -> bool:
        """
        Optimize index for better performance.

        Args:
            **options: Optimization options

        Returns:
            True if successful
        """
        if self.index is None:
            raise ProcessingError("No index to optimize")

        # FAISS optimization is typically done during index creation
        # This method can be used for additional optimization
        self.logger.info("Index optimization completed")
        return True

    def get_vector(self, vector_id: str) -> Optional[np.ndarray]:
        """Get vector by ID."""
        if self.index:
            return self.index.get_vector(vector_id)
        return None

    def get_metadata(self, vector_id: str) -> Optional[Dict[str, Any]]:
        """Get metadata by ID."""
        if self.index:
            return self.index.get_metadata(vector_id)
        return None

    def filter_by_metadata(
        self, filters: Dict[str, Any], limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Filter stored vectors by metadata.

        Args:
            filters: Metadata filter criteria
            limit: Maximum number of results

        Returns:
            List of matching result dicts with 'id', 'metadata', and 'vector'
        """
        if self.index is None or not hasattr(self.index, "metadata"):
            return []

        from .vector_store import _matches_filter

        if limit <= 0:
            return []

        results = []
        for vector_id, metadata in self.index.metadata.items():
            if _matches_filter(metadata, filters):
                results.append(
                    {
                        "id": vector_id,
                        "metadata": metadata,
                        "vector": self.get_vector(vector_id),
                    }
                )
                if len(results) >= limit:
                    break

        return results

    def scan_vectors(self, offset: int = 0, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Page through stored vectors in insertion order.

        Args:
            offset: Number of vectors to skip
            limit: Maximum number of vectors to return

        Returns:
            List of result dicts with 'id', 'metadata', and 'vector'
        """
        if self.index is None or limit <= 0:
            return []

        ids_page = self.index.vector_ids[offset:offset + limit]
        return [
            {
                "id": vector_id,
                "metadata": self.get_metadata(vector_id) or {},
                "vector": self.get_vector(vector_id),
            }
            for vector_id in ids_page
        ]

    def get_stats(self) -> Dict[str, Any]:
        """Get index statistics."""
        if self.index is None:
            return {"status": "no_index"}

        return {
            "index_type": self.index.index_type,
            "dimension": self.index.dimension,
            "vector_count": len(self.index.vector_ids),
            "faiss_available": FAISS_AVAILABLE,
        }

    def count(self) -> int:
        """Return the number of vectors currently tracked in this store.

        Returns the length of the ``vector_ids`` list maintained by
        ``FAISSIndex``.  FAISSStore does not implement vector deletion, so
        this list is strictly append-only and is always consistent with the
        underlying FAISS index (``index.ntotal``).
        """
        if self.index is None:
            return 0
        return len(self.index.vector_ids)
