"""
MCP Client Module

This module provides a generic MCP (Model Context Protocol) client implementation
for communicating with Python-based MCP servers and FastMCP servers via URL connections.

**IMPORTANT**: This implementation supports ONLY Python MCP servers and FastMCP servers.
JavaScript, TypeScript, C#, Java, and other language implementations are NOT supported.

Key Features:
    - URL-based connection (primary interface)
    - Generic JSON-RPC communication with Python/FastMCP servers
    - Support for HTTP, HTTPS, and SSE transports (auto-detected from URL)
    - Dynamic discovery of server capabilities
    - Authentication support (API keys, OAuth, custom headers)
    - Error handling and connection management

Main Classes:
    - MCPClient: Generic MCP client for Python/FastMCP MCP servers

Example Usage:
    >>> from semantica.ingest import MCPClient
    >>> # Connect via URL (primary method)
    >>> client = MCPClient(url="http://localhost:8000/mcp")
    >>> client.connect()
    >>> resources = client.list_resources()
    >>> tools = client.list_tools()
    >>> data = client.read_resource("resource://example")
    >>> result = client.call_tool("tool_name", {"param": "value"})

Author: Semantica Contributors
License: MIT
"""

import json
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from ..utils.exceptions import ProcessingError, ValidationError
from ..utils.logging import get_logger
from .ssrf import request_with_ssrf_guard


@dataclass
class MCPResource:
    """MCP resource representation."""

    uri: str
    name: str
    description: Optional[str] = None
    mime_type: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MCPTool:
    """MCP tool representation."""

    name: str
    description: Optional[str] = None
    input_schema: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


class MCPClient:
    """
    Generic MCP client for communicating with Python MCP servers and FastMCP servers.

    **IMPORTANT**: This client supports ONLY Python-based MCP servers and FastMCP servers.
    JavaScript, TypeScript, C#, Java, and other language implementations are NOT supported.

    This class provides a domain-agnostic implementation that works with
    any Python or FastMCP server following the MCP protocol specification.
    It supports URL-based connections and dynamically discovers server
    capabilities without requiring domain-specific code.

    Supported URL Schemes:
        - http://, https://: HTTP/HTTPS transport (auto-detected)
        - mcp://: MCP protocol URL (auto-detected as HTTP)
        - sse://: Server-Sent Events transport (auto-detected)

    Example Usage:
        >>> # Connect via URL (primary method)
        >>> client = MCPClient(url="http://localhost:8000/mcp")
        >>> client.connect()
        >>> resources = client.list_resources()
        >>> data = client.read_resource("resource://example")

        >>> # With authentication
        >>> client = MCPClient(
        ...     url="https://api.example.com/mcp",
        ...     headers={"Authorization": "Bearer token"}
        ... )
    """

    def __init__(
        self,
        url: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
        transport: Optional[str] = None,
        **config,
    ):
        """
        Initialize MCP client.

        **IMPORTANT**: Supports only Python MCP servers and FastMCP servers.

        Args:
            url: MCP server URL (primary parameter)
                - http://localhost:8000/mcp
                - https://api.example.com/mcp
                - mcp://server-name
            headers: Custom headers for authentication (e.g., {"Authorization": "Bearer token"})
            transport: Optional transport override (auto-detected from URL if not provided)
                - "http": HTTP/HTTPS transport
                - "sse": Server-Sent Events transport
            **config: Additional configuration options (timeout, etc.)

        Raises:
            ValidationError: If URL is invalid or transport cannot be determined
        """
        self.logger = get_logger("mcp_client")
        self.url = url
        self.headers = headers or {}
        self.config = config

        # Auto-detect transport from URL if not provided
        if url:
            parsed_url = url.lower()
            if parsed_url.startswith(("http://", "https://", "mcp://")):
                self.transport = "http"
            elif parsed_url.startswith("sse://"):
                self.transport = "sse"
            else:
                # Default to HTTP if scheme not recognized
                self.transport = "http"
                self.logger.warning(f"Unknown URL scheme, defaulting to HTTP: {url}")
        elif transport:
            self.transport = transport.lower()
        else:
            raise ValidationError(
                "Either 'url' or 'transport' parameter is required. "
                "URL-based connection is the primary method."
            )

        # Validate transport
        if self.transport not in ("http", "sse"):
            raise ValidationError(
                f"Unsupported transport: {self.transport}. "
                f"Supported: http, sse. "
                f"Note: stdio transport is not supported in public API."
            )

        # Validate URL for HTTP/SSE transports
        if self.transport in ("http", "sse") and not self.url:
            raise ValidationError(
                f"{self.transport} transport requires 'url' parameter"
            )

        # Internal stdio support (not exposed in public API)
        self._command: Optional[str] = None
        self._args: Optional[List[str]] = None

        # Connection state
        self._process: Optional[subprocess.Popen] = None
        self._connected: bool = False
        self._initialized: bool = False
        self._server_info: Optional[Dict[str, Any]] = None
        self._request_id: int = 0

        self.logger.debug(
            f"MCP client initialized: url={url}, transport={self.transport}"
        )

    def connect(self) -> bool:
        """
        Connect to MCP server via URL.

        **IMPORTANT**: Supports only Python MCP servers and FastMCP servers.

        Returns:
            bool: True if connection successful

        Raises:
            ProcessingError: If connection fails
        """
        try:
            if self.transport == "http":
                return self._connect_http()
            elif self.transport == "sse":
                return self._connect_sse()
            else:
                raise ValidationError(f"Unsupported transport: {self.transport}")
        except Exception as e:
            self.logger.error(f"Failed to connect to MCP server: {e}")
            raise ProcessingError(f"Failed to connect to MCP server: {e}") from e

    def _connect_stdio(self) -> bool:
        """Connect via stdio transport."""
        try:
            cmd = [self.command] + self.args
            self._process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=0,
            )
            self._connected = True
            self.logger.info("Connected to MCP server via stdio")

            # Initialize protocol
            return self._initialize()
        except Exception as e:
            self.logger.error(f"Failed to connect via stdio: {e}")
            raise

    def _connect_http(self) -> bool:
        """Connect via HTTP transport."""
        try:
            # HTTP transport will be implemented with requests/httpx
            # For now, mark as connected and initialize
            self._connected = True
            self.logger.info(f"Connected to MCP server via HTTP: {self.url}")
            return self._initialize()
        except Exception as e:
            self.logger.error(f"Failed to connect via HTTP: {e}")
            raise

    def _connect_sse(self) -> bool:
        """Connect via SSE transport."""
        try:
            # SSE transport will be implemented
            # For now, mark as connected and initialize
            self._connected = True
            self.logger.info(f"Connected to MCP server via SSE: {self.url}")
            return self._initialize()
        except Exception as e:
            self.logger.error(f"Failed to connect via SSE: {e}")
            raise

    def _initialize(self) -> bool:
        """Initialize MCP protocol."""
        try:
            request = {
                "jsonrpc": "2.0",
                "id": self._get_request_id(),
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"roots": {"listChanged": True}},
                    "clientInfo": {"name": "semantica", "version": "1.0.0"},
                },
            }

            response = self._send_request(request)

            if response and "result" in response:
                self._server_info = response["result"]
                self._initialized = True
                self.logger.info("MCP protocol initialized")
                return True
            else:
                error = response.get("error", {}) if response else {}
                raise ProcessingError(
                    f"Failed to initialize MCP: {error.get('message', 'Unknown error')}"
                )
        except Exception as e:
            self.logger.error(f"Failed to initialize MCP protocol: {e}")
            raise

    def disconnect(self):
        """Disconnect from MCP server."""
        if self._process:
            try:
                self._process.terminate()
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
            except Exception as e:
                self.logger.warning(f"Error disconnecting: {e}")
            finally:
                self._process = None

        self._connected = False
        self._initialized = False
        self.logger.info("Disconnected from MCP server")

    def _get_request_id(self) -> int:
        """Get next request ID."""
        self._request_id += 1
        return self._request_id

    def _send_request(self, request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Send JSON-RPC request to MCP server.

        Args:
            request: JSON-RPC request dictionary

        Returns:
            Response dictionary or None
        """
        if not self._connected:
            raise ProcessingError("Not connected to MCP server")

        try:
            if self.transport == "stdio":
                return self._send_request_stdio(request)
            elif self.transport == "http":
                return self._send_request_http(request)
            elif self.transport == "sse":
                return self._send_request_sse(request)
            else:
                raise ValidationError(f"Unsupported transport: {self.transport}")
        except Exception as e:
            self.logger.error(f"Failed to send request: {e}")
            raise ProcessingError(f"Failed to send request: {e}") from e

    def _send_request_stdio(self, request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Send request via stdio."""
        if not self._process:
            raise ProcessingError("Process not running")

        try:
            # Send request
            request_json = json.dumps(request) + "\n"
            self._process.stdin.write(request_json)
            self._process.stdin.flush()

            # Read response
            response_line = self._process.stdout.readline()
            if response_line:
                return json.loads(response_line.strip())
            return None
        except Exception as e:
            self.logger.error(f"Failed to send stdio request: {e}")
            raise

    def _send_request_http(self, request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Send request via HTTP, with redirect-safe credential handling.

        Uses ``request_with_ssrf_guard`` so that:

        * ``Authorization`` / ``Proxy-Authorization`` headers are **not**
          forwarded to a different origin if the MCP server issues a redirect
          (issue #947).
        * The redirect chain is bounded (default 10 hops).

        ``allow_private_ips=True`` is set because MCP servers are explicitly
        configured by the operator and frequently run on localhost or an
        internal network — the same trust model as ``allow_private_ips`` opt-in
        in the other ingestors.  That trust covers only ``self.url`` itself:
        ``allow_private_ips_on_redirect=False`` keeps redirect targets held to
        the normal public-address check, so a compromised or malicious MCP
        server cannot use a redirect to route the client into private/
        internal address space (e.g. cloud metadata) that the operator never
        configured.  Scheme validation (http/https only) and the
        auth-stripping logic remain active regardless of these flags.
        """
        try:
            response = request_with_ssrf_guard(
                "POST",
                self.url,
                headers=self.headers,
                json=request,
                timeout=self.config.get("timeout", 30.0),
                allow_private_ips=True,
                allow_private_ips_on_redirect=False,
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            self.logger.error(f"Failed to send HTTP request: {e}")
            raise

    def _send_request_sse(self, request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Send request via SSE."""
        # SSE implementation would go here
        # For now, raise not implemented
        raise ProcessingError("SSE transport not yet implemented")

    def list_resources(self) -> List[MCPResource]:
        """
        List resources available from MCP server.

        Returns:
            List of MCPResource objects
        """
        if not self._initialized:
            raise ProcessingError("MCP protocol not initialized")

        try:
            request = {
                "jsonrpc": "2.0",
                "id": self._get_request_id(),
                "method": "resources/list",
            }

            response = self._send_request(request)

            if response and "result" in response:
                resources_data = response["result"].get("resources", [])
                return [
                    MCPResource(
                        uri=r.get("uri", ""),
                        name=r.get("name", ""),
                        description=r.get("description"),
                        mime_type=r.get("mimeType"),
                        metadata=r.get("metadata", {}),
                    )
                    for r in resources_data
                ]
            else:
                error = response.get("error", {}) if response else {}
                raise ProcessingError(
                    f"Failed to list resources: {error.get('message', 'Unknown error')}"
                )
        except Exception as e:
            self.logger.error(f"Failed to list resources: {e}")
            raise

    def list_tools(self) -> List[MCPTool]:
        """
        List tools available from MCP server.

        Returns:
            List of MCPTool objects
        """
        if not self._initialized:
            raise ProcessingError("MCP protocol not initialized")

        try:
            request = {
                "jsonrpc": "2.0",
                "id": self._get_request_id(),
                "method": "tools/list",
            }

            response = self._send_request(request)

            if response and "result" in response:
                tools_data = response["result"].get("tools", [])
                return [
                    MCPTool(
                        name=t.get("name", ""),
                        description=t.get("description"),
                        input_schema=t.get("inputSchema", {}),
                        metadata=t.get("metadata", {}),
                    )
                    for t in tools_data
                ]
            else:
                error = response.get("error", {}) if response else {}
                raise ProcessingError(
                    f"Failed to list tools: {error.get('message', 'Unknown error')}"
                )
        except Exception as e:
            self.logger.error(f"Failed to list tools: {e}")
            raise

    def read_resource(self, uri: str) -> Dict[str, Any]:
        """
        Read a resource from MCP server.

        Args:
            uri: Resource URI

        Returns:
            Resource data dictionary
        """
        if not self._initialized:
            raise ProcessingError("MCP protocol not initialized")

        try:
            request = {
                "jsonrpc": "2.0",
                "id": self._get_request_id(),
                "method": "resources/read",
                "params": {"uri": uri},
            }

            response = self._send_request(request)

            if response and "result" in response:
                return response["result"]
            else:
                error = response.get("error", {}) if response else {}
                raise ProcessingError(
                    f"Failed to read resource: {error.get('message', 'Unknown error')}"
                )
        except Exception as e:
            self.logger.error(f"Failed to read resource {uri}: {e}")
            raise

    def call_tool(
        self, name: str, arguments: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Call a tool on MCP server.

        Args:
            name: Tool name
            arguments: Tool arguments

        Returns:
            Tool result dictionary
        """
        if not self._initialized:
            raise ProcessingError("MCP protocol not initialized")

        try:
            request = {
                "jsonrpc": "2.0",
                "id": self._get_request_id(),
                "method": "tools/call",
                "params": {"name": name, "arguments": arguments or {}},
            }

            response = self._send_request(request)

            if response and "result" in response:
                return response["result"]
            else:
                error = response.get("error", {}) if response else {}
                raise ProcessingError(
                    f"Failed to call tool {name}: {error.get('message', 'Unknown error')}"
                )
        except Exception as e:
            self.logger.error(f"Failed to call tool {name}: {e}")
            raise

    def is_connected(self) -> bool:
        """Check if connected to MCP server."""
        return self._connected and self._initialized

    def get_server_info(self) -> Optional[Dict[str, Any]]:
        """Get server information from initialization."""
        return self._server_info
