"""MCP server must report the package version, not a hardcoded string.

Regression test for #863: SERVER_INFO and the semantica://schema/info
resource used to hardcode "0.4.0", so MCP clients displayed a stale
version even when the installed package was newer.
"""

from semantica import __version__
from semantica.mcp_server import SERVER_INFO, _read_resource


def test_server_info_version_matches_package() -> None:
    assert SERVER_INFO["version"] == __version__


def test_schema_info_version_matches_package() -> None:
    resource = _read_resource("semantica://schema/info")
    assert resource["version"] == __version__
