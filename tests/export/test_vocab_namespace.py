"""@vocab in every JSON-LD context must be the namespace Semantica actually
ships (https://semantica.dev/ns#), not the dead /vocab/ that 404s.
"""

import json

from semantica.export.json_exporter import JSONExporter
from semantica.export.rdf_exporter import SEMANTICA_NS

KG = {
    "entities": [{"id": "https://example.org/e1", "text": "Acme", "type": "ORG"}],
    "relationships": [
        {"source_id": "e1", "target_id": "e2", "type": "employs"}
    ],
}


def _context_vocab(exporter, kind, tmp_path, name):
    path = tmp_path / name
    if kind == "knowledge_graph":
        exporter.export_knowledge_graph(KG, path, format="json-ld")
    elif kind == "entities":
        exporter.export_entities(KG["entities"], path, format="json-ld")
    elif kind == "relationships":
        exporter.export_relationships(KG["relationships"], path, format="json-ld")
    elif kind == "generic":
        exporter.export({"note": "plain payload, no @id"}, path, format="json-ld")
    else:
        raise AssertionError(kind)
    return json.loads(path.read_text())["@context"]["@vocab"]


def test_all_jsonld_contexts_pin_vocab_to_shipped_namespace(tmp_path):
    exporter = JSONExporter()
    for kind in ("knowledge_graph", "entities", "relationships", "generic"):
        assert _context_vocab(exporter, kind, tmp_path, f"{kind}.jsonld") == SEMANTICA_NS