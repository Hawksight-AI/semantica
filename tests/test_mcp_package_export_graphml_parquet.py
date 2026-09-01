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

    # ------------------------------------------------------------------
    # Regression: undeclared / wrongly-scoped GraphML keys.
    #
    # Pre-fix, _export_graphml declared:
    #   <key id="type"       for="node" …/>
    #   <key id="confidence" for="node" …/>
    #
    # and then referenced:
    #   <data key="label">     on BOTH nodes and edges (no declaration at all)
    #   <data key="confidence"> on edges (declared for="node" only)
    #
    # Schema-validating consumers (Cytoscape, yEd, any XSD-aware reader)
    # reject documents with undeclared or out-of-scope key references.
    # ------------------------------------------------------------------

    def _graphml_key_declarations(self, xml_text: str) -> dict:
        """Parse the XML and return {key_id: for_value} for every <key>."""
        import xml.etree.ElementTree as ET
        root = ET.fromstring(xml_text)
        ns = {"g": "http://graphml.graphdrawing.org/xmlns"}
        return {k.get("id"): k.get("for") for k in root.findall("g:key", ns)}

    def test_graphml_label_key_is_declared(self):
        """label key must be declared; pre-fix it was missing entirely."""
        from mcp.tools.export import handle_export_graph
        result = handle_export_graph({"format": "graphml"})
        self.assertNotIn("error", result, result)
        keys = self._graphml_key_declarations(result["data"])
        self.assertIn(
            "label", keys,
            f"<key id='label'> is missing from GraphML header; declared keys: {list(keys)}",
        )

    def test_graphml_label_key_scope_covers_edges(self):
        """label is written on both nodes (node label) and edges (edge type).
        Its for= scope must be 'all' or 'edge'.  Pre-fix it was not declared."""
        from mcp.tools.export import handle_export_graph
        result = handle_export_graph({"format": "graphml"})
        self.assertNotIn("error", result, result)
        keys = self._graphml_key_declarations(result["data"])
        scope = keys.get("label", "")
        self.assertIn(
            scope, ("all", "edge"),
            f"<key id='label'> has for={scope!r}; must be 'all' or 'edge' "
            f"because edges write <data key='label'>",
        )

    def test_graphml_confidence_key_scope_covers_edges(self):
        """confidence is written on both nodes and edges when include_attributes
        is True.  Pre-fix the key was declared for='node' only, making every
        edge confidence reference schema-invalid."""
        from mcp.tools.export import handle_export_graph
        result = handle_export_graph({"format": "graphml"})
        self.assertNotIn("error", result, result)
        keys = self._graphml_key_declarations(result["data"])
        scope = keys.get("confidence", "")
        self.assertIn(
            scope, ("all", "edge"),
            f"<key id='confidence'> has for={scope!r}; must be 'all' or 'edge' "
            f"because edges also write <data key='confidence'>",
        )

    def test_graphml_all_data_key_refs_are_declared(self):
        """Every <data key=X> reference in the document must have a matching
        <key id=X> declaration — with a graph that has both nodes AND edges,
        so edge-only violations are not hidden by an edge-free export."""
        import xml.etree.ElementTree as ET
        import tempfile
        from pathlib import Path
        from semantica.export import GraphExporter

        kg = {
            "entities": [
                {"id": "n1", "text": "Alice", "type": "Person"},
                {"id": "n2", "text": "Bob",   "type": "Person"},
            ],
            "relationships": [
                {"source_id": "n1", "target_id": "n2", "type": "knows"},
            ],
        }
        exporter = GraphExporter(format="graphml")
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir) / "out.graphml"
            exporter.export_knowledge_graph(kg, file_path=tmp_path)
            xml_text = tmp_path.read_text(encoding="utf-8")

        root = ET.fromstring(xml_text)
        ns = {"g": "http://graphml.graphdrawing.org/xmlns"}

        declared_ids = {k.get("id") for k in root.findall("g:key", ns)}
        referenced_ids = {d.get("key") for d in root.findall(".//g:data", ns)}

        undeclared = referenced_ids - declared_ids
        self.assertEqual(
            undeclared, set(),
            f"GraphML references key id(s) with no <key> declaration: {undeclared}. "
            f"Declared: {declared_ids}",
        )

    # ------------------------------------------------------------------
    # Regression: export() consumed nodes/edges while to_kg_dict() returns
    # entities/relationships — the GraphML was structurally valid XML but
    # silently contained zero nodes and zero edges.
    # ------------------------------------------------------------------

    def test_graphml_contains_graph_nodes(self):
        """Entities in the source graph must appear as <node> elements.
        Pre-fix: exporter.export(kg_dict) read 'nodes' key (absent in
        to_kg_dict()); export_knowledge_graph() converts entities -> nodes."""
        import xml.etree.ElementTree as ET
        from mcp.tools.export import handle_export_graph
        result = handle_export_graph({"format": "graphml"})
        self.assertNotIn("error", result, result)
        root = ET.fromstring(result["data"])
        ns = {"g": "http://graphml.graphdrawing.org/xmlns"}
        nodes = root.findall(".//g:node", ns)
        self.assertGreater(
            len(nodes), 0,
            "GraphML contains zero <node> elements; to_kg_dict() entities were "
            "not converted — export_knowledge_graph() must be used, not export().",
        )

    def test_graphml_contains_graph_edges(self):
        """Relationships in the source graph must appear as <edge> elements."""
        import xml.etree.ElementTree as ET
        from mcp.tools.export import handle_export_graph
        result = handle_export_graph({"format": "graphml"})
        self.assertNotIn("error", result, result)
        root = ET.fromstring(result["data"])
        ns = {"g": "http://graphml.graphdrawing.org/xmlns"}
        edges = root.findall(".//g:edge", ns)
        self.assertGreater(
            len(edges), 0,
            "GraphML contains zero <edge> elements; to_kg_dict() relationships were "
            "not converted — export_knowledge_graph() must be used, not export().",
        )

    def test_graphml_node_ids_match_source_graph(self):
        """The <node id=...> values must match the entity IDs from the source graph."""
        import xml.etree.ElementTree as ET
        from mcp.tools.export import handle_export_graph
        result = handle_export_graph({"format": "graphml"})
        self.assertNotIn("error", result, result)
        root = ET.fromstring(result["data"])
        ns = {"g": "http://graphml.graphdrawing.org/xmlns"}
        node_ids = {n.get("id") for n in root.findall(".//g:node", ns)}
        # _make_graph() adds nodes with id "n1" and "n2"
        self.assertIn("n1", node_ids, f"Expected 'n1' in GraphML node ids; got {node_ids}")
        self.assertIn("n2", node_ids, f"Expected 'n2' in GraphML node ids; got {node_ids}")

    # ------------------------------------------------------------------
    # Regression: XML-special characters in graph values must be escaped.
    # Pre-fix _export_graphml used bare f-string interpolation so a node
    # id of 'a&b' produced  <node id="a&b">  which is malformed XML.
    # ------------------------------------------------------------------

    def test_graphml_xml_special_chars_in_node_id_produce_well_formed_xml(self):
        """A node id containing & < > must be escaped in the id= attribute so
        the output remains well-formed XML.  Pre-fix this produced
        <node id="a&b"> which is a parse error."""
        import xml.etree.ElementTree as ET
        import mcp.session as _session
        from mcp.tools.export import handle_export_graph
        from semantica.context.context_graph import ContextGraph

        g = ContextGraph()
        g.add_node("a&b<c>d", node_type="entity")
        _orig = _session._graph
        _session._graph = g
        try:
            result = handle_export_graph({"format": "graphml"})
        finally:
            _session._graph = _orig

        self.assertNotIn("error", result, result)
        # Must parse without raising; pre-fix this raised ET.ParseError
        try:
            root = ET.fromstring(result["data"])
        except ET.ParseError as exc:
            self.fail(
                f"GraphML with special-char node id is malformed XML: {exc}\n"
                f"{result['data'][:600]}"
            )
        # The id attribute value must round-trip to the original string
        ns = {"g": "http://graphml.graphdrawing.org/xmlns"}
        node_ids = {n.get("id") for n in root.findall(".//g:node", ns)}
        self.assertIn(
            "a&b<c>d", node_ids,
            f"Node id did not round-trip correctly; got {node_ids}",
        )

    def test_graphml_xml_special_chars_in_label_produce_well_formed_xml(self):
        """A label containing & < > must be escaped in the <data> text
        node.  Pre-fix <data key="label">A & B</data> is malformed XML.

        Drives GraphExporter directly with a hand-crafted KG dict to avoid
        relying on ContextGraph internal field mapping."""
        import xml.etree.ElementTree as ET
        import tempfile
        from pathlib import Path
        from semantica.export import GraphExporter

        special_label = "price < 100 & qty > 0"
        kg = {
            "entities": [
                {"id": "e1", "text": special_label, "type": "metric"},
            ],
            "relationships": [],
        }

        exporter = GraphExporter(format="graphml")
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir) / "out.graphml"
            exporter.export_knowledge_graph(kg, file_path=tmp_path)
            xml_text = tmp_path.read_text(encoding="utf-8")

        # Must parse without error
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as exc:
            self.fail(
                f"GraphML with special-char label is malformed XML: {exc}\n"
                f"{xml_text[:600]}"
            )
        # Label text must round-trip to the original string
        ns = {"g": "http://graphml.graphdrawing.org/xmlns"}
        data_texts = [
            d.text
            for d in root.findall(".//g:data", ns)
            if d.get("key") == "label"
        ]
        self.assertIn(
            special_label, data_texts,
            f"Label text did not round-trip; found label data: {data_texts}",
        )

    def test_graphml_double_quotes_in_node_id_produce_well_formed_xml(self):
        """A node id containing double-quotes must not break the id=\" attribute
        boundary.  Pre-fix: <node id="say "hi""> is malformed."""
        import xml.etree.ElementTree as ET
        import mcp.session as _session
        from mcp.tools.export import handle_export_graph
        from semantica.context.context_graph import ContextGraph

        g = ContextGraph()
        g.add_node('say "hi"', node_type="entity")
        _orig = _session._graph
        _session._graph = g
        try:
            result = handle_export_graph({"format": "graphml"})
        finally:
            _session._graph = _orig

        self.assertNotIn("error", result, result)
        try:
            root = ET.fromstring(result["data"])
        except ET.ParseError as exc:
            self.fail(
                f"GraphML with double-quote node id is malformed XML: {exc}\n"
                f"{result['data'][:600]}"
            )
        ns = {"g": "http://graphml.graphdrawing.org/xmlns"}
        node_ids = {n.get("id") for n in root.findall(".//g:node", ns)}
        self.assertIn(
            'say "hi"', node_ids,
            f"Node id with double-quotes did not round-trip; got {node_ids}",
        )

    def test_graphml_xml_special_chars_in_edge_source_target_produce_well_formed_xml(self):
        """Edge source= and target= attributes must also be escaped."""
        import xml.etree.ElementTree as ET
        import mcp.session as _session
        from mcp.tools.export import handle_export_graph
        from semantica.context.context_graph import ContextGraph

        g = ContextGraph()
        g.add_node("src&node", node_type="entity")
        g.add_node("tgt<node>", node_type="entity")
        g.add_edge("src&node", "tgt<node>", "link")
        _orig = _session._graph
        _session._graph = g
        try:
            result = handle_export_graph({"format": "graphml"})
        finally:
            _session._graph = _orig

        self.assertNotIn("error", result, result)
        try:
            root = ET.fromstring(result["data"])
        except ET.ParseError as exc:
            self.fail(
                f"GraphML with special-char edge endpoints is malformed XML: {exc}\n"
                f"{result['data'][:600]}"
            )
        ns = {"g": "http://graphml.graphdrawing.org/xmlns"}
        edge_els = root.findall(".//g:edge", ns)
        self.assertEqual(len(edge_els), 1, "Expected exactly one edge element")
        self.assertEqual(edge_els[0].get("source"), "src&node")
        self.assertEqual(edge_els[0].get("target"), "tgt<node>")


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
