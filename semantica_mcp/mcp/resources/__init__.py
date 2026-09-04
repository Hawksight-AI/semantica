"""
MCP resource registry — static and dynamic resources exposed via resources/list
and resources/read.
"""

from .registry import RESOURCE_DEFINITIONS, handle_resource_read

__all__ = ["RESOURCE_DEFINITIONS", "handle_resource_read"]
