"""
Result Caching Module

This module provides caching mechanisms for extraction results to avoid redundant
computations and API calls. It implements an LRU (Least Recently Used) cache
with Time-To-Live (TTL) support.

Key Features:
    - LRU Caching: Evicts least recently used items when cache is full
    - TTL Support: Expires items after a configurable duration
    - Namespaced Caching: Separate caches for entities, relations, and triplets
    - Hash-based Keys: Uses stable hashing for text and parameters

Classes:
    - ExtractionCache: Main cache manager
    - CacheItem: Container for cached data with metadata

Author: Semantica Contributors
License: MIT
"""

import copy
import time
import hashlib
import json
from collections import OrderedDict
from typing import Any, Dict, Optional, Union, List
from threading import Lock

from ..utils.logging import get_logger

# Sentinel distinguishing "no entry under this key" from a stored None.
_MISSING = object()


class CacheItem:
    """Container for cached data.

    Holds a private snapshot: callers own what get() hands them, and the
    stored value is immune to later mutation of the list the caller passed
    to set(). Without the snapshot, extraction results were handed out by
    reference and post-processing (weighted-confidence reblending, boundary
    correction) rewrote the CACHED entities in place — every later cache hit
    returned already-mutated objects, and a non-idempotent transform like
    calculate_weighted_confidence compounded on each hit.

    A value that cannot be deep-copied is stored as-is: the writer's result
    still caches (the common values — dataclasses of primitives — always
    copy), and get() treats an uncopyable entry as a miss rather than
    failing the extraction over cached data.
    """
    def __init__(self, value: Any, ttl: Optional[int] = None):
        try:
            self.value = copy.deepcopy(value)
        except Exception:
            self.value = value
        self.timestamp = time.time()
        self.ttl = ttl

    def is_expired(self) -> bool:
        """Check if item has expired."""
        if self.ttl is None:
            return False
        return time.time() - self.timestamp > self.ttl

class ExtractionCache:
    """
    LRU Cache for extraction results.
    Thread-safe implementation.
    """
    def __init__(self, max_size: int = 1000, ttl: int = 3600):
        """
        Initialize the cache.
        
        Args:
            max_size: Maximum number of items to store per namespace
            ttl: Time to live in seconds (default 1 hour)
        """
        self.max_size = max_size
        self.ttl = ttl
        self._caches: Dict[str, OrderedDict] = {
            "entities": OrderedDict(),
            "relations": OrderedDict(),
            "triplets": OrderedDict()
        }
        self._locks: Dict[str, Lock] = {
            "entities": Lock(),
            "relations": Lock(),
            "triplets": Lock()
        }
        self.logger = get_logger("extraction_cache")
        self.enabled = True

    def _generate_key(self, text: str, **params) -> str:
        """
        Generate a stable cache key based on text and parameters.
        
        Note: Sensitive parameters like 'api_key' are excluded from the cache key
        to prevent security risks and ensure cache sharing where appropriate.
        """
        # Filter out sensitive keys
        sensitive_keys = {'api_key', 'token', 'password', 'secret', 'auth', 'authorization'}
        filtered_params = {k: v for k, v in params.items() if k.lower() not in sensitive_keys}

        # Create a stable string representation of params
        # Sort keys to ensure consistent ordering
        param_str = json.dumps(filtered_params, sort_keys=True, default=str)
        
        # Combine text and params
        content = f"{text}|{param_str}"
        
        # Return hash (SHA-256 for better security than MD5)
        return hashlib.sha256(content.encode('utf-8')).hexdigest()

    def get(self, namespace: str, text: str, **params) -> Optional[Any]:
        """
        Retrieve item from cache.
        
        Args:
            namespace: Cache namespace ("entities", "relations", "triplets")
            text: Input text used for extraction
            **params: Extraction parameters used
            
        Returns:
            Cached result or None if not found/expired
        """
        if not self.enabled:
            return None

        if namespace not in self._caches:
            return None

        key = self._generate_key(text, **params)
        
        item_value = _MISSING
        with self._locks[namespace]:
            cache = self._caches[namespace]
            if key in cache:
                item = cache[key]
                
                # Check expiration
                if item.is_expired():
                    del cache[key]
                    return None
                
                # Move to end (mark as recently used)
                cache.move_to_end(key)
                # Capture the snapshot reference under the lock; the deep
                # copy happens after release so lock hold time stays flat
                # regardless of result size.
                item_value = item.value

        if item_value is _MISSING:
            return None
        # A copy, not the stored snapshot: the caller owns what comes back
        # and may post-process it in place, and that must never reach the
        # next reader of this entry. A value that cannot be copied is a
        # corrupt entry — treat it as a miss and evict rather than fail the
        # extraction over cached data.
        try:
            return copy.deepcopy(item_value)
        except Exception:
            self.logger.warning(
                "Cached value could not be copied; treating as a miss"
            )
            with self._locks[namespace]:
                self._caches[namespace].pop(key, None)
            return None

    def set(self, namespace: str, text: str, value: Any, **params) -> None:
        """
        Add item to cache.
        
        Args:
            namespace: Cache namespace
            text: Input text
            value: Result to cache
            **params: Extraction parameters
        """
        if not self.enabled:
            return

        if namespace not in self._caches:
            self.logger.warning(f"Unknown cache namespace: {namespace}")
            return

        key = self._generate_key(text, **params)
        item = CacheItem(value, self.ttl)
        
        with self._locks[namespace]:
            cache = self._caches[namespace]
            
            # If key exists, update and move to end
            if key in cache:
                cache.move_to_end(key)
            
            cache[key] = item
            
            # Evict if full
            if len(cache) > self.max_size:
                cache.popitem(last=False)  # Remove first (least recently used)

    def clear(self, namespace: Optional[str] = None):
        """Clear cache(s)."""
        if namespace:
            if namespace in self._caches:
                with self._locks[namespace]:
                    self._caches[namespace].clear()
        else:
            for ns in self._caches:
                with self._locks[ns]:
                    self._caches[ns].clear()

    def get_stats(self) -> Dict[str, Dict[str, int]]:
        """Get cache statistics."""
        stats = {}
        for ns, cache in self._caches.items():
            stats[ns] = {
                "size": len(cache),
                "max_size": self.max_size
            }
        return stats

# Global cache instance
extraction_cache = ExtractionCache()
