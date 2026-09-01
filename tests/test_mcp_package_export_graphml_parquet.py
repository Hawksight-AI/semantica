"""Regression tests for MCP export_graph — GraphML and Parquet branches.

Pre-fix bugs
------------
GraphML:
  - handle_export_graph({"format": "graphml"}) imported ``GraphMLExporter``
    which does not exist in ``semantica.export``, raising ImportError on every
    call and returning ``{"error": "...GraphMLExporter..."}``.
  - Even if the import were corrected, ``exporter.export(graph)`` passed the
    raw ContextGraph object and ignored the required ``file_path`` argument.
    ``GraphExporter.export()`` writes to a file and returns ``None``; the old
    code used its return value as the response data.

Parquet:
  - ``exporter.export(graph, include_metadata)`` passed the ContextGraph object
    as ``data`` (not the kg dict) and ``include_metadata`` (a bool) as
    ``file_path``.  Both arguments are wrong: the exporter expects a list/dict
    of plain dicts as ``data`` and a filesystem path as ``file_path``.
  - ``ParquetExporter.export()`` returns ``None``; wrapping it in ``str()``
    always produced the string ``"None"`` as the response data.

Post-fix expectations
---------------------
GraphML:
  - Returns ``{"format": "graphml", "data": "<graphml ...>..."}``
  - ``data`` is a non-empty string containing valid GraphML XML.
  - The TemporaryDirectory is cleaned up after the call (no leaked temp files).

Parquet:
  - Returns ``{"format": "parquet", "data": {...}, "encoding": "base64"}``
  - ``data`` is a dict mapping filename → base64-encoded bytes.
  - At least one ``*.parquet`` key is present.
  - Each value decodes to non-empty bytes (valid Parquet file magic: b"PAR1").
"""

from __future__ import annotations

import base64
import os
import unittest

# Disable progress tracking before any Semantica import so no singleton
# writes to stdout during testing.
os.environ["SEMANTICA_DISABLE_PROGRESS"] = "1"


def _make_graph():
    """Return a ContextGraph with two entities and one relationship."""
    from semantica.context.context_graph import ContextGraph
    g = ContextGraph()
    g.add_node("n1", node_type="entity")
    g.add_node("n2", node_type="entity")
    g.add_edge("n1", "n2", "related_to")
    return g


class TestMCPExportGraphML(unittest.TestCase):
    """GraphML export must use GraphExporter (not GraphMLExporter) and return
    valid GraphML XML."""

    def setUp(self):
        import mcp.session as _session
        self._orig = _session._graph
        _session._graph = _make_graph()

    def tearDown(self):
        import mcp.session as _session
        _session._graph = self._orig

    # ------------------------------------------------------------------
    # Regression: old code raised ImportError for GraphMLExporter
    # ------------------------------------------------------------------

    def test_graphml_does_not_return_import_error(self):
        """The old code: ``from semantica.export import GraphMLExporter`` —
        that class does not exist.  Result must not contain 'GraphMLExporter'
        in the error message."""
        from mcp.tools.export import handle_export_graph
        result = handle_export_graph({"format": "graphml"})
        if "error" in result:
            self.assertNotIn(
                "GraphMLExporter", result["error"],
                f"Import of non-existent GraphMLExporter still present: {result}",
            )

    # ------------------------------------------------------------------
    # Correctness
    # ------------------------------------------------------------------

    def test_graphml_returns_success_not_error(self):
        from mcp.tools.export import handle_export_graph
        result = handle_export_graph({"format": "graphml"})
        self.assertNotIn("error", result, f"GraphML export returned error: {result}")

    def test_graphml_format_key_is_correct(self):
        from mcp.tools.export import handle_export_graph
        result = handle_export_graph({"format": "graphml"})
        self.assertNotIn("error", result, result)
        self.assertEqual(result.get("format"), "graphml")

    def test_graphml_data_is_non_empty_string(self):
        from mcp.tools.export import handle_export_graph
        result = handle_export_graph({"format": "graphml"})
        self.assertNotIn("error", result, result)
        self.assertIsInstance(result.get("data"), str)
        self.assertGreater(len(result["data"]), 0)

    def test_graphml_data_contains_xml_declaration(self):
        from mcp.tools.export import handle_export_graph
        result = handle_export_graph({"format": "graphml"})
        self.assertNotIn("error", result, result)
        self.assertIn('<?xml version="1.0"', result["data"])

    def test_graphml_data_contains_graphml_element(self):
        from mcp.tools.export import handle_export_graph
        result = handle_export_graph({"format": "graphml"})
        self.assertNotIn("error", result, result)
        self.assertIn("<graphml", result["data"])
        self.assertIn("</graphml>", result["data"])

    def test_graphml_data_is_not_the_string_None(self):
        """The old code called ``str(exporter.export(graph))`` which returns
        ``'None'`` because ``export()`` returns ``None``."""
        from mcp.tools.export import handle_export_graph
        result = handle_export_graph({"format": "graphml"})
        self.assertNotIn("error", result, result)
        self.assertNotEqual(result.get("data"), "None")

    def test_graphml_is_parseable_xml(self):
        """The response must be well-formed XML, not an error string."""
        import xml.etree.ElementTree as ET
        from mcp.tools.export import handle_export_graph
        result = handle_export_graph({"format": "graphml"})
        self.assertNotIn("error", result, result)
        try:
            ET.fromstring(result["data"])
        except ET.ParseError as exc:
            self.fail(f"GraphML output is not valid XML: {exc}\n{result['data'][:500]}")

    def test_graphml_no_contextgraph_attribute_error(self):
        """The old code passed the ContextGraph object directly.  Verify the
        error 'ContextGraph' object has no attribute 'get' (or similar) is gone."""
        from mcp.tools.export import handle_export_graph
        result = handle_export_graph({"format": "graphml"})
        if "error" in result:
            self.assertNotIn("ContextGraph", result["error"])
            self.assertNotIn("has no attribute", result["error"])


class TestMCPExportParquet(unittest.TestCase):
    """Parquet export must use export_knowledge_graph(), return base64-encoded
    Parquet bytes, and clean up temporary files."""

    def setUp(self):
        import mcp.session as _session
        self._orig = _session._graph
        _session._graph = _make_graph()

    def tearDown(self):
        import mcp.session as _session
        _session._graph = self._orig

    def _skip_if_no_pyarrow(self):
        try:
            import pyarrow  # noqa: F401
        except ImportError:
            self.skipTest("pyarrow not installed")

    # ------------------------------------------------------------------
    # Regression: old code produced {"format": "parquet", "data": "None"}
    # ------------------------------------------------------------------

    def test_parquet_data_is_not_the_string_None(self):
        """The old code: ``str(exporter.export(graph, include_metadata))``
        always produced ``"None"``."""
        self._skip_if_no_pyarrow()
        from mcp.tools.export import handle_export_graph
        result = handle_export_graph({"format": "parquet"})
        self.assertNotIn("error", result, result)
        self.assertNotEqual(result.get("data"), "None")
        self.assertNotEqual(result.get("data"), None)

    # ------------------------------------------------------------------
    # Regression: old code passed ContextGraph and bool to export()
    # ------------------------------------------------------------------

    def test_parquet_does_not_return_contextgraph_type_error(self):
        """The old code passed a ContextGraph as ``data`` and bool as
        ``file_path``.  Ensure neither TypeError appears in the result."""
        self._skip_if_no_pyarrow()
        from mcp.tools.export import handle_export_graph
        result = handle_export_graph({"format": "parquet"})
        if "error" in result:
            self.assertNotIn("ContextGraph", result["error"])
            self.assertNotIn("file_path", result["error"])

    # ------------------------------------------------------------------
    # Correctness
    # ------------------------------------------------------------------

    def test_parquet_returns_success_not_error(self):
        self._skip_if_no_pyarrow()
        from mcp.tools.export import handle_export_graph
        result = handle_export_graph({"format": "parquet"})
        self.assertNotIn("error", result, f"Parquet export returned error: {result}")

    def test_parquet_format_key_is_correct(self):
        self._skip_if_no_pyarrow()
        from mcp.tools.export import handle_export_graph
        result = handle_export_graph({"format": "parquet"})
        self.assertNotIn("error", result, result)
        self.assertEqual(result.get("format"), "parquet")

    def test_parquet_encoding_is_base64(self):
        self._skip_if_no_pyarrow()
        from mcp.tools.export import handle_export_graph
        result = handle_export_graph({"format": "parquet"})
        self.assertNotIn("error", result, result)
        self.assertEqual(result.get("encoding"), "base64")

    def test_parquet_data_is_dict_of_filenames_to_strings(self):
        self._skip_if_no_pyarrow()
        from mcp.tools.export import handle_export_graph
        result = handle_export_graph({"format": "parquet"})
        self.assertNotIn("error", result, result)
        data = result.get("data")
        self.assertIsInstance(data, dict, f"Expected dict, got {type(data)}: {data!r}")
        for k, v in data.items():
            self.assertIsInstance(k, str, f"key {k!r} is not str")
            self.assertIsInstance(v, str, f"value for {k!r} is not str")

    def test_parquet_data_contains_at_least_one_parquet_file(self):
        self._skip_if_no_pyarrow()
        from mcp.tools.export import handle_export_graph
        result = handle_export_graph({"format": "parquet"})
        self.assertNotIn("error", result, result)
        data = result.get("data", {})
        parquet_keys = [k for k in data if k.endswith(".parquet")]
        self.assertGreater(len(parquet_keys), 0,
                           f"No .parquet keys in data: {list(data.keys())}")

    def test_parquet_values_decode_to_valid_parquet_magic(self):
        """Each base64 value must decode to bytes starting with the Parquet
        magic number b'PAR1' (first 4 bytes)."""
        self._skip_if_no_pyarrow()
        from mcp.tools.export import handle_export_graph
        result = handle_export_graph({"format": "parquet"})
        self.assertNotIn("error", result, result)
        data = result.get("data", {})
        for filename, b64_str in data.items():
            raw = base64.b64decode(b64_str)
            self.assertGreater(len(raw), 4, f"{filename}: decoded to {len(raw)} bytes")
            self.assertEqual(
                raw[:4], b"PAR1",
                f"{filename}: expected Parquet magic b'PAR1', got {raw[:4]!r}",
            )

    def test_parquet_no_pyarrow_returns_graceful_error(self):
        """When pyarrow is absent the handler must return a dict with 'error'
        key, not raise an exception.  Simulate by patching the import."""
        import sys
        from mcp.tools.export import handle_export_graph
        # Temporarily hide pyarrow
        real_pyarrow = sys.modules.pop("pyarrow", None)
        # Also hide the real ParquetExporter so the import inside the handler fails
        import semantica.export as _export_mod
        real_exporter_class = _export_mod.ParquetExporter
        # Replace with the dummy that raises ImportError on init
        class _MissingParquet:
            def __init__(self, *a, **kw):
                raise ImportError("pyarrow is not installed")
        _export_mod.ParquetExporter = _MissingParquet
        try:
            result = handle_export_graph({"format": "parquet"})
            self.assertIn("error", result)
            self.assertIn("pyarrow", result["error"].lower())
        finally:
            _export_mod.ParquetExporter = real_exporter_class
            if real_pyarrow is not None:
                sys.modules["pyarrow"] = real_pyarrow


class TestMCPExportPreservesExistingFormats(unittest.TestCase):
    """Adding GraphML/Parquet fixes must not regress JSON, CSV, or RDF."""

    def setUp(self):
        import mcp.session as _session
        self._orig = _session._graph
        _session._graph = _make_graph()

    def tearDown(self):
        import mcp.session as _session
        _session._graph = self._orig

    def test_json_still_works(self):
        from mcp.tools.export import handle_export_graph
        result = handle_export_graph({"format": "json"})
        self.assertNotIn("error", result, result)
        self.assertEqual(result.get("format"), "json")
        self.assertIsInstance(result.get("data"), dict)

    def test_csv_still_works(self):
        from mcp.tools.export import handle_export_graph
        result = handle_export_graph({"format": "csv"})
        self.assertNotIn("error", result, result)
        self.assertEqual(result.get("format"), "csv")
        self.assertIn("id,label,type", result.get("data", ""))

    def test_turtle_still_works(self):
        from mcp.tools.export import handle_export_graph
        result = handle_export_graph({"format": "turtle"})
        self.assertNotIn("error", result, result)
        self.assertIsInstance(result.get("data"), str)
        self.assertIn("@prefix", result["data"])

    def test_nt_still_works(self):
        from mcp.tools.export import handle_export_graph
        result = handle_export_graph({"format": "nt"})
        self.assertNotIn("error", result, result)
        self.assertIsInstance(result.get("data"), str)
        self.assertGreater(len(result["data"]), 0)

    def test_unsupported_format_still_returns_error(self):
        from mcp.tools.export import handle_export_graph
        result = handle_export_graph({"format": "yaml"})
        self.assertIn("error", result)


if __name__ == "__main__":
    unittest.main()
