"""Shared types for LLM provider interfaces."""

from typing import Dict, List, Union

JSONValue = Union[
    str,
    int,
    float,
    bool,
    None,
    Dict[str, "JSONValue"],
    List["JSONValue"],
]

__all__ = ["JSONValue"]
