"""
Helper Utilities Module

This module contains shared utility functions used across different modules of the
Semantica framework, providing common data manipulation, file handling, string
processing, date/time operations, and configuration management capabilities.

Key Features:
    - Data formatting and serialization (JSON, YAML)
    - Text cleaning and normalization
    - Entity normalization and hashing
    - File and directory operations
    - Timestamp formatting and parsing
    - Dictionary manipulation (merge, flatten, nested access)
    - List chunking and batch processing
    - Retry decorators for error handling

Main Functions:
    - format_data: Format data into JSON, YAML, or other formats
    - clean_text: Clean and normalize text strings
    - normalize_entities: Normalize entity dictionaries to consistent format
    - hash_data: Generate hash for data (string, bytes, or dictionary)
    - safe_filename: Generate safe filename from string
    - ensure_directory: Ensure directory exists, create if needed
    - read_json_file: Read JSON file safely
    - write_json_file: Write data to JSON file safely
    - format_timestamp: Format timestamp to string
    - parse_timestamp: Parse timestamp string to datetime
    - merge_dicts: Merge multiple dictionaries (deep merge support)
    - chunk_list: Split list into chunks of specified size
    - flatten_dict: Flatten nested dictionary
    - get_nested_value: Get nested dictionary value by dot-separated path
    - set_nested_value: Set nested dictionary value by dot-separated path
    - retry_on_error: Decorator for retrying function on error
    - safe_import: Safely import optional modules, handling ImportError and OSError

Example Usage:
    >>> from semantica.utils import clean_text, normalize_entities
    >>> cleaned = clean_text("  Hello   World  ")
    >>> entities = normalize_entities([{"id": "e1", "text": "John", "type": "PERSON"}])
    >>> 
    >>> from semantica.utils import hash_data, safe_filename
    >>> data_hash = hash_data({"key": "value"})
    >>> safe_name = safe_filename("my file.txt")
    >>> 
    >>> from semantica.utils import merge_dicts, get_nested_value
    >>> merged = merge_dicts({"a": 1}, {"b": 2}, deep=True)
    >>> value = get_nested_value(config, "database.host", default="localhost")
    >>> 
    >>> from semantica.utils import retry_on_error
    >>> @retry_on_error(max_retries=3, delay=1.0)
    ... def fetch_data():
    ...     return api_call()

Author: Semantica Contributors
License: MIT
"""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import re
import types
from collections import Counter
from collections.abc import Iterable as IterableABC
from collections.abc import Mapping
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple, Type, Union

from .exceptions import ProcessingError, ValidationError


def format_data(data: Any, format_type: str = "json") -> str:
    """
    Format data into specified format.

    Args:
        data: Data to format
        format_type: Format type ('json', 'yaml', 'xml', 'csv')

    Returns:
        Formatted data string

    Raises:
        ValueError: If format_type is not supported
    """
    if format_type == "json":
        return json.dumps(data, indent=2, ensure_ascii=False)
    elif format_type == "yaml":
        try:
            import yaml

            return yaml.dump(data, default_flow_style=False)
        except (ImportError, OSError):
            raise ValueError("PyYAML not installed. Install with: pip install pyyaml")
    else:
        raise ValueError(f"Unsupported format type: {format_type}")


def clean_text(text: str, preserve_whitespace: bool = False) -> str:
    """
    Clean and normalize text.

    Removes extra whitespace, normalizes line breaks, and handles
    common text issues.

    Args:
        text: Text to clean
        preserve_whitespace: If True, preserve significant whitespace

    Returns:
        Cleaned text string
    """
    if not text:
        return ""

    # Remove leading/trailing whitespace
    text = text.strip()

    if not preserve_whitespace:
        # Normalize multiple spaces to single space
        text = re.sub(r"\s+", " ", text)
        # Normalize line breaks
        text = re.sub(r"\n\s*\n", "\n", text)

    # Remove zero-width characters
    text = re.sub(r"[\u200b-\u200d\ufeff]", "", text)

    return text


def normalize_entities(entities: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Normalize entity dictionaries to consistent format.

    Ensures all entities have required fields and consistent structure.

    Args:
        entities: List of entity dictionaries

    Returns:
        List of normalized entity dictionaries
    """
    normalized = []

    for entity in entities:
        normalized_entity = {
            "id": entity.get("id") or entity.get("entity_id"),
            "text": entity.get("text") or entity.get("label") or entity.get("name"),
            "type": entity.get("type") or entity.get("entity_type"),
            "confidence": entity.get("confidence", 1.0),
            "start": entity.get("start") or entity.get("start_offset"),
            "end": entity.get("end") or entity.get("end_offset"),
        }

        # Add optional fields if present
        if "metadata" in entity:
            normalized_entity["metadata"] = entity["metadata"]
        if "relations" in entity:
            normalized_entity["relations"] = entity["relations"]

        normalized.append(normalized_entity)

    return normalized


def hash_data(data: Union[str, bytes, Dict[str, Any]]) -> str:
    """
    Generate hash for data.

    Args:
        data: Data to hash (string, bytes, or dictionary)

    Returns:
        Hexadecimal hash string
    """
    if isinstance(data, dict):
        # Sort keys for consistent hashing
        data_str = json.dumps(data, sort_keys=True)
        data = data_str.encode("utf-8")
    elif isinstance(data, str):
        data = data.encode("utf-8")

    return hashlib.sha256(data).hexdigest()


def safe_filename(filename: str, max_length: int = 255) -> str:
    """
    Generate safe filename from string.

    Removes invalid characters and ensures filename is safe for filesystem.

    Args:
        filename: Original filename
        max_length: Maximum length of filename

    Returns:
        Safe filename string
    """
    # Remove invalid characters
    filename = re.sub(r'[<>:"/\\|?*]', "", filename)

    # Replace spaces with underscores
    filename = filename.replace(" ", "_")

    # Remove leading/trailing dots and spaces
    filename = filename.strip(". ")

    # Truncate if too long
    if len(filename) > max_length:
        name, ext = os.path.splitext(filename)
        max_name_length = max_length - len(ext)
        filename = name[:max_name_length] + ext

    return filename or "unnamed"


def ensure_directory(path: Union[str, Path]) -> Path:
    """
    Ensure directory exists, create if it doesn't.

    Args:
        path: Directory path

    Returns:
        Path object for the directory
    """
    dir_path = Path(path)
    dir_path.mkdir(parents=True, exist_ok=True)
    return dir_path


def read_json_file(filepath: Union[str, Path]) -> Dict[str, Any]:
    """
    Read JSON file safely.

    Args:
        filepath: Path to JSON file

    Returns:
        Parsed JSON data

    Raises:
        FileNotFoundError: If file doesn't exist
        json.JSONDecodeError: If file contains invalid JSON
    """
    filepath = Path(filepath)
    if not filepath.exists():
        raise FileNotFoundError(f"File not found: {filepath}")

    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json_file(
    data: Dict[str, Any],
    filepath: Union[str, Path],
    indent: int = 2,
    ensure_ascii: bool = False,
) -> None:
    """
    Write data to JSON file safely.

    Args:
        data: Data to write
        filepath: Path to JSON file
        indent: JSON indentation level
        ensure_ascii: Whether to ensure ASCII encoding
    """
    filepath = Path(filepath)
    ensure_directory(filepath.parent)

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=indent, ensure_ascii=ensure_ascii)


def get_file_size(filepath: Union[str, Path]) -> int:
    """
    Get file size in bytes.

    Args:
        filepath: Path to file

    Returns:
        File size in bytes
    """
    return Path(filepath).stat().st_size


def format_timestamp(
    timestamp: Optional[Union[datetime, float, int]] = None,
    format_str: str = "%Y-%m-%d %H:%M:%S",
    timezone_aware: bool = True,
) -> str:
    """
    Format timestamp to string.

    Args:
        timestamp: Timestamp (datetime, float, or int). If None, uses current time.
        format_str: DateTime format string
        timezone_aware: Whether to include timezone information

    Returns:
        Formatted timestamp string
    """
    if timestamp is None:
        dt = datetime.now(timezone.utc if timezone_aware else None)
    elif isinstance(timestamp, (int, float)):
        dt = datetime.fromtimestamp(timestamp, timezone.utc if timezone_aware else None)
    elif isinstance(timestamp, datetime):
        dt = timestamp
    else:
        raise ValueError(f"Invalid timestamp type: {type(timestamp)}")

    return dt.strftime(format_str)


def parse_timestamp(timestamp_str: str, format_str: Optional[str] = None) -> datetime:
    """
    Parse timestamp string to datetime.

    Args:
        timestamp_str: Timestamp string
        format_str: DateTime format string. If None, tries common formats.

    Returns:
        Parsed datetime object
    """
    if format_str:
        return datetime.strptime(timestamp_str, format_str)

    # Try common formats
    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%m/%d/%Y",
    ]

    for fmt in formats:
        try:
            return datetime.strptime(timestamp_str, fmt)
        except ValueError:
            continue

    raise ValueError(f"Could not parse timestamp: {timestamp_str}")


def merge_dicts(*dicts: Dict[str, Any], deep: bool = True) -> Dict[str, Any]:
    """
    Merge multiple dictionaries.

    Args:
        *dicts: Dictionaries to merge
        deep: If True, perform deep merge for nested dictionaries

    Returns:
        Merged dictionary
    """
    if not dicts:
        return {}

    result = {}

    for d in dicts:
        if not isinstance(d, dict):
            continue

        for key, value in d.items():
            if (
                deep
                and key in result
                and isinstance(result[key], dict)
                and isinstance(value, dict)
            ):
                result[key] = merge_dicts(result[key], value, deep=True)
            else:
                result[key] = value

    return result


def chunk_list(items: List[Any], chunk_size: int) -> List[List[Any]]:
    """
    Split list into chunks of specified size.

    Args:
        items: List to chunk
        chunk_size: Size of each chunk

    Returns:
        List of chunks
    """
    return [items[i : i + chunk_size] for i in range(0, len(items), chunk_size)]    
def flatten_dict(
    d: Dict[str, Any], parent_key: str = "", sep: str = "."
) -> Dict[str, Any]:
    """
    Flatten nested dictionary.

    Args:
        d: Dictionary to flatten
        parent_key: Parent key prefix
        sep: Separator for nested keys

    Returns:
        Flattened dictionary

    Raises:
        ValueError: If two input paths produce the same flattened key.
    """
    result = {}

    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k

        if isinstance(v, dict):
            nested = flatten_dict(v, new_key, sep=sep)

            for key, value in nested.items():
                if key in result:
                    raise ValueError(
                        f"Key collision while flattening dictionary: {key}"
                    )
                result[key] = value
        else:
            if new_key in result:
                raise ValueError(
                    f"Key collision while flattening dictionary: {new_key}"
                )
            result[new_key] = v

    return result


def get_nested_value(
    d: Dict[str, Any], key_path: str, default: Any = None, sep: str = "."
) -> Any:
    """
    Get nested dictionary value by dot-separated key path.

    Args:
        d: Dictionary
        key_path: Dot-separated key path (e.g., "config.database.host")
        default: Default value if key not found
        sep: Separator for key path

    Returns:
        Value at key path or default
    """
    keys = key_path.split(sep)
    value = d

    for key in keys:
        if isinstance(value, dict) and key in value:
            value = value[key]
        else:
            return default

    return value


def set_nested_value(
    d: Dict[str, Any], key_path: str, value: Any, sep: str = "."
) -> None:
    """
    Set nested dictionary value by dot-separated key path.

    Args:
        d: Dictionary to modify
        key_path: Dot-separated key path (e.g., "config.database.host")
        value: Value to set
        sep: Separator for key path
    """
    keys = key_path.split(sep)

    for key in keys[:-1]:
        if key not in d:
            d[key] = {}
        d = d[key]

    d[keys[-1]] = value


def safe_import(
    module_name: str,
    package: Optional[str] = None,
    default: Any = None,
    error_message: Optional[str] = None,
) -> Tuple[Any, bool]:
    """
    Safely import an optional module, handling both ImportError and OSError.
    
    This is useful for optional dependencies that may fail to import due to:
    - Missing package (ImportError)
    - DLL loading failures on Windows, e.g., PyTorch (OSError)
    
    Args:
        module_name: Name of the module to import (e.g., "spacy", "docling.document_converter")
        package: Optional package name for relative imports
        default: Default value to return if import fails
        error_message: Optional custom error message for logging
        
    Returns:
        Tuple of (module_or_default, success_flag):
        - If import succeeds: (imported_module, True)
        - If import fails: (default, False)
        
    Example:
        >>> spacy, available = safe_import("spacy")
        >>> if available:
        ...     doc = spacy.load("en_core_web_sm")
        >>> 
        >>> converter, available = safe_import("docling.document_converter", default=None)
        >>> if available:
        ...     converter = converter()
    """
    try:
        if package:
            module = importlib.import_module(module_name, package=package)
        else:
            module = importlib.import_module(module_name)
        return module, True
    except (ImportError, ModuleNotFoundError, OSError) as e:
        if error_message:
            import sys
            if "logging" in sys.modules:
                from .logging import get_logger
                logger = get_logger("utils.helpers")
                logger.debug(f"{error_message}: {e}")
        return default, False


def retry_on_error(
    max_retries: int = 3,
    delay: float = 1.0,
    backoff_factor: float = 2.0,
    exceptions: Tuple[type[Exception], ...] = (Exception,),
):
    """
    Decorator for retrying function on error.

    Args:
        max_retries: Maximum number of retries
        delay: Initial delay between retries in seconds
        backoff_factor: Backoff multiplier for delay
        exceptions: Tuple of exception types to catch

    Returns:
        Decorator function
    """
    import functools
    import time

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            current_delay = delay
            last_exception = None

            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_retries:
                        time.sleep(current_delay)
                        current_delay *= backoff_factor
                    else:
                        raise

            raise last_exception

        return wrapper

    return decorator


def classify_path_distance(hop_count: int) -> str:
    """Classify a path hop count into a human-readable distance band.

    Bands:
        "direct"    — 0–1 hops (single edge or self)
        "near"      — 2–3 hops (closely related)
        "mid-range" — 4–6 hops (reachable but separated)
        "distant"   — 7+ hops (weakly coupled)

    This is the single source of truth for distance-band thresholds used by
    both the Explorer API (PathResponse.distance_band) and the KGVisualizer
    (highlight_path edge styling).
    """
    if hop_count <= 1:
        return "direct"
    if hop_count <= 3:
        return "near"
    if hop_count <= 6:
        return "mid-range"
    return "distant"


# Graph payloads circulate under two vocabularies: 'entities'/'relationships'
# (kg builders, most exporters) and 'nodes'/'edges' (ContextGraph.to_dict,
# Neo4jCSVExporter, the Explorer routes). Consumers each reconciled them
# locally, with at least three competing idioms, so the same payload could be
# exported, silently dropped, or rejected depending on which consumer read it.
# This is the single place that decision is made.
_ENTITY_KEYS = ("entities", "nodes")
_RELATIONSHIP_KEYS = ("relationships", "edges")
_TRIPLET_KEYS = ("triplets",)

# Keys that legitimately travel alongside the collections without being
# records themselves, so their presence is never evidence that records were
# dropped: ContextGraph.to_dict() carries 'statistics', JSON envelopes carry
# 'metadata' and 'count'.
_CONTEXT_KEYS = ("metadata", "statistics", "count")


def _require_recognized_keys(
    payload: Mapping, recognized_keys: Sequence[str], *, what: str
) -> None:
    """Reject a mapping that shares no key with the recognized set.

    A consumer that reads a fixed set of keys turns an unrecognized mapping
    into an empty result that looks like a legitimate one. An empty mapping is
    allowed through -- it carries nothing that could be lost.

    Args:
        payload: Mapping to check.
        recognized_keys: Keys the consumer reads.
        what: Noun for the error message, e.g. ``"Graph payload"``.

    Raises:
        ValidationError: if ``payload`` is non-empty and shares no key with
            ``recognized_keys``.
    """
    if not payload or any(key in payload for key in recognized_keys):
        return

    supplied = ", ".join(f"'{key}'" for key in sorted(map(str, payload)))
    expected = ", ".join(f"'{key}'" for key in recognized_keys)
    raise ValidationError(
        f"{what} has no recognized key. Supplied: {supplied}. "
        f"Expected at least one of: {expected}."
    )


def _require_nothing_dropped(
    payload: Mapping,
    recognized_keys: Sequence[str],
    resolved: Iterable[Any],
    *,
    what: str,
) -> None:
    """Reject a mapping that resolved to nothing while still holding records.

    Checking that a recognized key is *present* is not enough:
    ``{"entities": [], "data": [...]}`` clears that bar and still resolves to
    empty, dropping every record under 'data'. Presence answers "did the
    caller use our vocabulary"; this answers the question that actually
    matters, "did anything the caller supplied survive".

    Only non-empty lists count as evidence of dropped records. A payload can
    carry scalars and dicts that are not collections -- ContextGraph.to_dict()
    always includes 'statistics' -- and an empty graph must stay exportable.

    Args:
        payload: Mapping to check.
        recognized_keys: Keys the consumer reads.
        resolved: The collections the consumer resolved from ``payload``.
        what: Noun for the error message, e.g. ``"Graph payload"``.

    Raises:
        ValidationError: if nothing resolved and an unread key holds a
            non-empty list.
    """
    if any(resolved):
        return

    dropped = sorted(
        str(key)
        for key, value in payload.items()
        if key not in recognized_keys
        and key not in _CONTEXT_KEYS
        and isinstance(value, (list, tuple))
        and value
    )
    if not dropped:
        return

    named = ", ".join(f"'{key}'" for key in dropped)
    expected = ", ".join(f"'{key}'" for key in recognized_keys)
    raise ValidationError(
        f"{what} resolved to nothing, but {named} still holds records. "
        f"Exporting it would drop them silently. Supply the records under "
        f"one of: {expected}."
    )


def _is_record(value: Any) -> bool:
    """Report whether a value can stand in for a graph record.

    Consumers read records either as mappings (``entity.get("type")`` in the
    LPG and Arango exporters) or as objects with attributes
    (``Neo4jCSVExporter._record_to_dict`` accepts dataclasses and anything
    carrying a ``__dict__``). Both are legitimate, so both are accepted here;
    strings, numbers, and nested sequences are not records under either
    reading.

    Modules and class/type objects are excluded even though they carry
    ``__dict__``: they are not graph records under any supported reading, and
    passing them through the boundary would produce ``AttributeError`` inside
    exporters rather than a ``ValidationError`` at the boundary where the
    problem is visible.
    """
    return isinstance(value, Mapping) or is_dataclass(value) or (
        hasattr(value, "__dict__")
        and not isinstance(value, (types.ModuleType, type))
    )


def _record_to_dict(record: Any) -> Dict[str, Any]:
    """Convert an accepted record to a plain dict.

    :func:`_is_record` accepts mappings, dataclasses, and objects carrying
    ``__dict__`` as legitimate record shapes, but consumers of
    :func:`normalize_graph_payload` -- YAML serialization, ``entity.get(...)``
    in the LPG and Arango exporters -- read records as dicts. Converting here,
    at the boundary, means every exporter gets the same shape regardless of
    which reading the caller used; previously only ``Neo4jCSVExporter``
    converted object-shaped records locally, so a dataclass record passed
    validation for the other exporters only to crash with a raw
    ``AttributeError`` once used.
    """
    if isinstance(record, Mapping):
        return dict(record)
    if is_dataclass(record):
        return asdict(record)
    return {
        key: value for key, value in vars(record).items() if not key.startswith("_")
    }


def _coerce_records(key: str, value: Any) -> List[Any]:
    """Validate one collection value and materialize it as a list of records.

    This runs before any truthiness or ``list()`` call, because both mislead
    on malformed input: ``list("abc")`` quietly turns a string into three
    single-character "records", and ``list(42)`` raises a bare ``TypeError``
    from deep inside the exporter that named the exporter rather than the
    offending payload key. Neither reaches the caller as an actionable
    message, so the shapes that produce them are rejected by name instead.

    ``None`` is deliberately not rejected: JSON round-trips an absent
    collection to null, and treating that as "no records under this key" is
    the same answer an explicit ``[]`` gets. It is not silent data loss --
    a null collection alongside records under an unread key is still caught
    by :func:`_require_nothing_dropped`.

    Args:
        key: Payload key the value came from, for the error message.
        value: The raw value stored under ``key``.

    Returns:
        The records as a new list, so the result never aliases the input.

    Raises:
        ValidationError: if ``value`` is a string, bytes, a mapping, or any
            non-iterable scalar; or if any element is not a record.
    """
    if value is None:
        return []

    if isinstance(value, (str, bytes, bytearray)):
        raise ValidationError(
            f"Graph payload key '{key}' holds a {type(value).__name__}, not a "
            f"collection of records. Iterating it would yield characters, not "
            f"records. Supply a list of records."
        )

    if isinstance(value, Mapping):
        raise ValidationError(
            f"Graph payload key '{key}' holds a mapping, not a collection of "
            f"records. If it is a single record, wrap it in a list; if it is "
            f"keyed by ID, supply its values as a list."
        )

    if not isinstance(value, IterableABC):
        raise ValidationError(
            f"Graph payload key '{key}' holds a "
            f"{type(value).__name__}, not a collection of records. Supply a "
            f"list of records."
        )

    records = list(value)
    for index, record in enumerate(records):
        if not _is_record(record):
            raise ValidationError(
                f"Graph payload key '{key}' holds a "
                f"{type(record).__name__} at index {index}, not a record. "
                f"Records must be mappings or objects with attributes."
            )
    return [_record_to_dict(record) for record in records]


def _canonical_record_multiset(records: List[Dict[str, Any]]) -> "Counter[str]":
    """Represent records as an order-independent multiset for equality checks.

    Two spellings of the same collection (``entities`` and ``nodes``) can
    legitimately list identical records in a different order -- a caller
    round-tripping through a dict-keyed cache or a set has no reason to
    preserve list order. Comparing with plain list equality would treat that
    as a conflict and reject a payload that carries no real data loss, so
    records are compared as a multiset of their canonical JSON form instead.
    """
    return Counter(
        json.dumps(record, sort_keys=True, default=str) for record in records
    )


def _resolve_collection(
    payload: Dict[str, Any], keys: Tuple[str, ...]
) -> List[Dict[str, Any]]:
    """Pick one collection from a payload that may use either vocabulary.

    Both spellings may legitimately be present: ``JSONExporter`` writes
    'entities' and 'nodes' side by side, so a round-trip of its output carries
    both, one of them empty. Where only one holds records, that one wins.

    Two non-empty, unequal spellings are a different matter -- there is no
    basis for preferring either, and picking one would silently discard the
    other -- so that is refused rather than guessed at.

    Every spelling present is validated, not just the one that wins: a
    malformed 'nodes' alongside a well-formed 'entities' is a payload the
    caller should hear about, and validating only the winner would let it
    through on the strength of the other key.

    Args:
        payload: Mapping to read from.
        keys: Accepted spellings, most canonical first.

    Returns:
        The resolved collection, or an empty list if no spelling is present.

    Raises:
        ValidationError: if a spelling holds something other than a collection
            of records; or if two spellings are both present, both non-empty,
            and hold different records, order ignored.
    """
    present = {
        key: _coerce_records(key, payload[key]) for key in keys if key in payload
    }
    populated = {key: value for key, value in present.items() if value}

    if len(populated) > 1:
        values = list(populated.values())
        canonical = [_canonical_record_multiset(value) for value in values]
        if any(entry != canonical[0] for entry in canonical[1:]):
            named = " and ".join(f"'{key}'" for key in populated)
            raise ValidationError(
                f"Graph payload carries {named} with different contents; "
                f"cannot determine which to export. Supply one, or make them "
                f"identical."
            )

    for key in keys:
        value = present.get(key)
        if value:
            # Already a fresh list from _coerce_records, so the result cannot
            # alias the caller's collection.
            return value

    # Every spelling present is empty (or none is): an explicit empty
    # collection is a legitimate answer, distinct from "unrecognized".
    return []


def _require_mapping(data: Any, expected_keys: Sequence[str]) -> None:
    """Reject non-mapping export input with an actionable error.

    Shared by every consumer of :func:`normalize_graph_payload` so that a
    wrong *type* fails the same way everywhere. Handed a sequence (or any
    other non-mapping), every downstream key lookup would fail with a bare
    ``AttributeError: 'list' object has no attribute 'get'``, which tells the
    caller nothing about the shape expected -- and ``normalize_graph_payload``
    itself raises ``ValidationError`` for this case, which would leave
    exporters that skip this guard raising a different exception type than
    the ones that call it, for the identical mistake.

    A list is rejected rather than wrapped: these formats distinguish
    entities from relationships from triplets (or nodes/edges), so inferring
    which one a bare list represents would silently mislabel the records.

    Args:
        data: Candidate export payload.
        expected_keys: Key names the caller reads, named in the error so the
            caller learns the expected shape.

    Raises:
        ProcessingError: if ``data`` is not a mapping.
    """
    if not isinstance(data, Mapping):
        keys = "/".join(f"'{key}'" for key in expected_keys)
        raise ProcessingError(
            f"Cannot export object of type '{type(data).__name__}': "
            f"expected a dict with {keys}."
        )


def normalize_graph_payload(
    payload: Dict[str, Any],
) -> Dict[str, List[Dict[str, Any]]]:
    """Reduce a graph payload to one canonical vocabulary.

    Accepts either 'entities'/'relationships' or 'nodes'/'edges' (or a mix)
    and returns the canonical spelling, so consumers read one shape instead of
    reimplementing the reconciliation.

    This is the validation boundary for graph payloads: it either returns
    collections of records or raises. Nothing that reaches an exporter through
    it needs re-checking, and nothing malformed passes through it as a
    valid-looking empty graph.

    Args:
        payload: Graph payload mapping.

    Returns:
        ``{"entities": [...], "relationships": [...], "triplets": [...]}``.

    Raises:
        ValidationError: if ``payload`` is not a mapping; if a recognized key
            holds something other than a collection of records; if two
            spellings of the same collection are both non-empty and differ; if
            a non-empty mapping contains no recognized key; or if it resolves
            to nothing while an unread key still holds records. The last two
            would otherwise hand the caller a valid-looking result with their
            records silently dropped.

    Example:
        >>> normalize_graph_payload({"nodes": [{"id": "n1"}], "edges": []})
        {'entities': [{'id': 'n1'}], 'relationships': [], 'triplets': []}
    """
    if not isinstance(payload, Mapping):
        raise ValidationError(
            f"Cannot normalize graph payload of type "
            f"'{type(payload).__name__}': expected a mapping."
        )

    recognized = _ENTITY_KEYS + _RELATIONSHIP_KEYS + _TRIPLET_KEYS
    _require_recognized_keys(payload, recognized, what="Graph payload")

    resolved = {
        "entities": _resolve_collection(payload, _ENTITY_KEYS),
        "relationships": _resolve_collection(payload, _RELATIONSHIP_KEYS),
        "triplets": _resolve_collection(payload, _TRIPLET_KEYS),
    }

    _require_nothing_dropped(
        payload, recognized, resolved.values(), what="Graph payload"
    )

    return resolved
