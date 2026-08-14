import unittest
from unittest.mock import MagicMock, patch

from semantica.kg.graph_builder import GraphBuilder


class TestGraphBuilderExternal(unittest.TestCase):
    def setUp(self):
        self.mock_tracker_patcher = patch("semantica.utils.progress_tracker.get_progress_tracker")
        self.mock_get_tracker = self.mock_tracker_patcher.start()
        self.mock_tracker = MagicMock()
        self.mock_get_tracker.return_value = self.mock_tracker

        self.mock_resolver_patcher = patch("semantica.kg.entity_resolver.EntityResolver")
        self.mock_resolver_cls = self.mock_resolver_patcher.start()

        self.mock_conflict_patcher = patch("semantica.conflicts.conflict_detector.ConflictDetector")
        self.mock_conflict_cls = self.mock_conflict_patcher.start()

    def tearDown(self):
        self.mock_tracker_patcher.stop()
        self.mock_resolver_patcher.stop()
        self.mock_conflict_patcher.stop()

    def test_single_source_dict_with_source_id_target_id(self):
        builder = GraphBuilder(merge_entities=False, resolve_conflicts=False)

        entities = [
            {"id": "drug:1", "name": "Aspirin", "type": "Drug"},
            {"id": "disease:1", "name": "Myocardial infarction", "type": "Disease"},
        ]
        relationships = [
            {"source_id": "drug:1", "target_id": "disease:1", "type": "TREATS"},
        ]

        source = {"entities": entities, "relationships": relationships}

        kg = builder.build(source)

        self.assertEqual(len(kg["entities"]), 2)
        self.assertEqual(len(kg["relationships"]), 1)
        rel = kg["relationships"][0]
        self.assertEqual(rel.get("source"), "drug:1")
        self.assertEqual(rel.get("target"), "disease:1")
        self.assertEqual(kg["metadata"]["num_relationships"], 1)

    def test_sources_list_merge_with_external_relationships(self):
        builder = GraphBuilder(merge_entities=False, resolve_conflicts=False)

        source1 = {
            "entities": [{"id": "1", "name": "A"}],
            "relationships": [{"source_id": "1", "target_id": "2", "type": "REL_1"}],
        }
        source2 = {
            "entities": [{"id": "2", "name": "B"}],
            "relationships": [{"source_id": "2", "target_id": "1", "type": "REL_2"}],
        }

        kg = builder.build([source1, source2])

        self.assertEqual(len(kg["entities"]), 2)
        self.assertEqual(len(kg["relationships"]), 2)
        sources = {r["source"] for r in kg["relationships"]}
        targets = {r["target"] for r in kg["relationships"]}
        self.assertEqual(sources, {"1", "2"})
        self.assertEqual(targets, {"1", "2"})

    def test_build_with_explicit_relationships_argument_external_ids(self):
        builder = GraphBuilder(merge_entities=False, resolve_conflicts=False)

        entities = [
            {"id": "1", "name": "A"},
            {"id": "2", "name": "B"},
        ]
        relationships = [
            {"source_id": "1", "target_id": "2", "type": "REL"},
        ]

        kg = builder.build(entities, relationships=relationships)

        self.assertEqual(len(kg["entities"]), 2)
        self.assertEqual(len(kg["relationships"]), 1)
        rel = kg["relationships"][0]
        self.assertEqual(rel.get("source"), "1")
        self.assertEqual(rel.get("target"), "2")

    def test_build_single_source_external_graph(self):
        builder = GraphBuilder(merge_entities=False, resolve_conflicts=False)

        source = {
            "entities": [{"id": "1", "name": "A"}],
            "relationships": [{"source_id": "1", "target_id": "1", "type": "SELF"}],
        }

        kg = builder.build_single_source(source)

        self.assertEqual(len(kg["entities"]), 1)
        self.assertEqual(len(kg["relationships"]), 1)
        rel = kg["relationships"][0]
        self.assertEqual(rel.get("source"), "1")
        self.assertEqual(rel.get("target"), "1")

    def test_relationship_key_variants_normalized(self):
        builder = GraphBuilder(merge_entities=False, resolve_conflicts=False)

        entities = [
            {"id": "1", "name": "A"},
            {"id": "2", "name": "B"},
            {"id": "3", "name": "C"},
            {"id": "4", "name": "D"},
        ]
        relationships = [
            {"source_id": "1", "target_id": "2", "type": "R1"},
            {"source": "2", "target": "3", "type": "R2"},
            {"subject": "3", "object": "4", "type": "R3"},
        ]

        kg = builder.build({"entities": entities, "relationships": relationships})

        self.assertEqual(len(kg["relationships"]), 3)
        ids = {(r["source"], r["target"]) for r in kg["relationships"]}
        self.assertIn(("1", "2"), ids)
        self.assertIn(("2", "3"), ids)
        self.assertIn(("3", "4"), ids)

    def test_relationship_endpoints_are_remapped_after_entity_resolution(self):
        builder = GraphBuilder(merge_entities=False, resolve_conflicts=False)
        resolver = MagicMock()
        resolver.resolve_entities.return_value = [
            {
                "id": "alice:1",
                "name": "Alice Chen",
                "type": "Person",
                "merged_from": ["alice:1", "alice:2"],
            },
            {"id": "org:1", "name": "Zyx Qqqq", "type": "Organization"},
        ]

        graph = builder.build(
            {
                "entities": [
                    {"id": "alice:1", "name": "Alice Chen", "type": "Person"},
                    {"id": "alice:2", "name": "Alice Chen", "type": "Person"},
                    {"id": "org:1", "name": "Zyx Qqqq", "type": "Organization"},
                ],
                "relationships": [
                    {
                        "source": "alice:2",
                        "target": "org:1",
                        "type": "WORKS_FOR",
                    }
                ],
            },
            entity_resolver=resolver,
        )

        self.assertEqual(
            graph["relationships"],
            [{"source": "alice:1", "target": "org:1", "type": "WORKS_FOR"}],
        )
        entity_ids = {entity["id"] for entity in graph["entities"]}
        for relationship in graph["relationships"]:
            self.assertIn(relationship["source"], entity_ids)
            self.assertIn(relationship["target"], entity_ids)

    def test_unhashable_entity_ids_do_not_crash_remapping(self):
        builder = GraphBuilder(merge_entities=False, resolve_conflicts=False)
        resolver = MagicMock()
        resolver.resolve_entities.return_value = [
            {
                "id": ["invalid-canonical-id"],
                "name": "Invalid ID",
                "type": "Person",
                "merged_from": ["invalid-canonical-id"],
            },
            {
                "id": "alice:1",
                "name": "Alice Chen",
                "type": "Person",
                "merged_from": [["invalid-source-id"]],
            },
        ]

        graph = builder.build(
            {
                "entities": [{"id": "alice:1", "name": "Alice Chen", "type": "Person"}],
                "relationships": [],
            },
            entity_resolver=resolver,
        )

        self.assertEqual(len(graph["entities"]), 2)

    def test_relationship_remapping_skips_unmerged_entities(self):
        builder = GraphBuilder(merge_entities=False, resolve_conflicts=False)
        resolver = MagicMock()
        resolver.resolve_entities.return_value = [
            {"id": "alice:1", "name": "Alice Chen", "type": "Person"},
            {"id": "org:1", "name": "Zyx Qqqq", "type": "Organization"},
        ]

        with patch.object(builder, "_remap_relationship_endpoints") as remap:
            builder.build(
                {
                    "entities": [
                        {"id": "alice:1", "name": "Alice Chen", "type": "Person"},
                        {"id": "org:1", "name": "Zyx Qqqq", "type": "Organization"},
                    ],
                    "relationships": [],
                },
                entity_resolver=resolver,
            )

        remap.assert_not_called()

    def test_warning_when_all_relationships_dropped(self):
        builder = GraphBuilder(merge_entities=False, resolve_conflicts=False)

        source = {
            "entities": [],
            "relationships": [{"foo": "x"}, {"bar": "y"}],
        }

        with patch.object(builder.logger, "warning") as mock_warning:
            kg = builder.build(source)

        self.assertEqual(len(kg["relationships"]), 0)
        mock_warning.assert_called()
        args, _ = mock_warning.call_args
        self.assertIn("All relationships were dropped", args[0])

    def test_no_warning_when_some_relationships_kept(self):
        builder = GraphBuilder(merge_entities=False, resolve_conflicts=False)

        source = {
            "entities": [{"id": "1"}, {"id": "2"}],
            "relationships": [
                {"source_id": "1", "target_id": "2", "type": "REL"},
                {"foo": "x"},
            ],
        }

        with patch.object(builder.logger, "warning") as mock_warning:
            kg = builder.build(source)

        self.assertEqual(len(kg["relationships"]), 2)
        mock_warning.assert_not_called()

    def test_issue_208_minimal_reproduction_shape(self):
        builder = GraphBuilder(
            merge_entities=False,
            entity_resolution_strategy="none",
            resolve_conflicts=False,
        )

        entities = [
            {"id": "e1", "name": "Entity 1"},
            {"id": "e2", "name": "Entity 2"},
            {"id": "e3", "name": "Entity 3"},
        ]
        relationships = [
            {"source_id": "e1", "target_id": "e2", "type": "REL_1"},
            {"source_id": "e2", "target_id": "e3", "type": "REL_2"},
        ]

        entity_ids = {e["id"] for e in entities}
        for r in relationships:
            self.assertIn(r["source_id"], entity_ids)
            self.assertIn(r["target_id"], entity_ids)

        kg = builder.build(
            sources=[{"entities": entities, "relationships": relationships}],
            merge_entities=False,
        )

        self.assertEqual(len(kg["entities"]), 3)
        self.assertEqual(len(kg["relationships"]), 2)
        pairs = {(r["source"], r["target"]) for r in kg["relationships"]}
        self.assertIn(("e1", "e2"), pairs)
        self.assertIn(("e2", "e3"), pairs)

    def test_issue_206_earnings_call_shape(self):
        builder = GraphBuilder(
            merge_entities=False,
            entity_resolution_strategy="none",
            resolve_conflicts=False,
        )

        entities = [
            {
                "id": "entity_446_MDA Space Ltd.",
                "name": "MDA Space Ltd.",
                "type": "ORGANIZATION",
            },
            {
                "id": "entity_500_$409.8 million",
                "name": "$409.8 million",
                "type": "MONEY",
            },
        ]

        relationships = [
            {
                "id": None,
                "source_id": "MDA Space Ltd.",
                "target_id": "$409.8 million",
                "type": "HAS_REVENUE",
                "confidence": 0.975,
                "metadata": {},
            }
        ]

        kg = builder.build(
            sources=[{"entities": entities, "relationships": relationships}],
            merge_entities=False,
        )

        self.assertEqual(len(kg["entities"]), 2)
        self.assertEqual(len(kg["relationships"]), 1)
        rel = kg["relationships"][0]
        self.assertEqual(rel.get("source"), "MDA Space Ltd.")
        self.assertEqual(rel.get("target"), "$409.8 million")
