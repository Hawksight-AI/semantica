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
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Type, Union

from .exceptions import ValidationError


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
    """
    items = []

    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k

        if isinstance(v, dict):
            items.extend(flatten_dict(v, new_key, sep=sep).items())
        else:
            items.append((new_key, v))

    return dict(items)


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

    Args:
        payload: Mapping to read from.
        keys: Accepted spellings, most canonical first.

    Returns:
        The resolved collection, or an empty list if no spelling is present.

    Raises:
        ValidationError: if two spellings are both present, both non-empty,
            and not equal.
    """
    present = {key: payload[key] for key in keys if key in payload}
    populated = {key: value for key, value in present.items() if value}

    if len(populated) > 1:
        values = list(populated.values())
        if any(value != values[0] for value in values[1:]):
            named = " and ".join(f"'{key}'" for key in populated)
            raise ValidationError(
                f"Graph payload carries {named} with different contents; "
                f"cannot determine which to export. Supply one, or make them "
                f"identical."
            )

    for key in keys:
        value = present.get(key)
        if value:
            return list(value)

    # Every spelling present is empty (or none is): an explicit empty
    # collection is a legitimate answer, distinct from "unrecognized".
    return []


def normalize_graph_payload(
    payload: Dict[str, Any], *, require_recognized: bool = True
) -> Dict[str, List[Dict[str, Any]]]:
    """Reduce a graph payload to one canonical vocabulary.

    Accepts either 'entities'/'relationships' or 'nodes'/'edges' (or a mix)
    and returns the canonical spelling, so consumers read one shape instead of
    reimplementing the reconciliation.

    Args:
        payload: Graph payload mapping.
        require_recognized: When True (default), a non-empty mapping that
            shares no key with the recognized set raises rather than returning
            empty collections -- returning empty would hand the caller a
            valid-looking result with their records silently dropped. Pass
            False when an unrecognized payload should degrade to empty.

    Returns:
        ``{"entities": [...], "relationships": [...], "triplets": [...]}``.

    Raises:
        ValidationError: if ``payload`` is not a mapping; if two spellings of
            the same collection are both non-empty and differ; or, when
            ``require_recognized`` is True, if a non-empty mapping contains no
            recognized key.

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
    if require_recognized and payload and not any(key in payload for key in recognized):
        supplied = ", ".join(f"'{key}'" for key in sorted(map(str, payload)))
        expected = ", ".join(f"'{key}'" for key in recognized)
        raise ValidationError(
            f"Graph payload has no recognized key. Supplied: {supplied}. "
            f"Expected at least one of: {expected}."
        )

    return {
        "entities": _resolve_collection(payload, _ENTITY_KEYS),
        "relationships": _resolve_collection(payload, _RELATIONSHIP_KEYS),
        "triplets": _resolve_collection(payload, _TRIPLET_KEYS),
    }
