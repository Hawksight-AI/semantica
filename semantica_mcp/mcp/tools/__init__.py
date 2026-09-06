"""
MCP tool registry — imports all tool handlers and assembles TOOL_DEFINITIONS.

Each module under mcp/tools/ registers its handlers here.
"""

from .decisions import DECISION_TOOLS
from .export import EXPORT_TOOLS
from .extraction import EXTRACTION_TOOLS
from .graph import GRAPH_TOOLS
from .reasoning import REASONING_TOOLS

# Ordered list — exposed to the MCP client via tools/list
TOOL_DEFINITIONS = (
    EXTRACTION_TOOLS
    + DECISION_TOOLS
    + GRAPH_TOOLS
    + REASONING_TOOLS
    + EXPORT_TOOLS
)

__all__ = ["TOOL_DEFINITIONS"]
