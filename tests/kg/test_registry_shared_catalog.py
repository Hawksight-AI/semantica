"""Copy-on-write behavior for the shared built-in algorithm catalog (#1177).

The built-in catalog is built once at import; instances bind it by reference
and copy before their first mutation, so constructing an AlgorithmRegistry no
longer replays the 14 built-in ``register`` calls, and no instance's
mutations can leak into the shared catalog or into other instances.
"""

import unittest
from unittest.mock import patch

from semantica.kg.registry import (
    _BUILTIN_ALGORITHMS,
    AlgorithmRegistry,
    algorithm_registry,
)


class SharedBuiltinCatalogTests(unittest.TestCase):
    def test_construction_binds_shared_catalog_without_replaying_registers(self):
        registry = AlgorithmRegistry()
        self.assertIs(registry._algorithms, _BUILTIN_ALGORITHMS)

        with patch.object(
            AlgorithmRegistry, "register", side_effect=AssertionError("replayed")
        ):
            AlgorithmRegistry()  # must not call register()

    def test_builtin_catalog_is_fully_populated(self):
        listing = algorithm_registry.list_all()
        self.assertEqual(
            sorted(listing),
            [
                "centrality",
                "community_detection",
                "embeddings",
                "link_prediction",
                "path_finding",
                "similarity",
            ],
        )
        self.assertEqual(listing["similarity"], ["cosine", "euclidean", "manhattan", "correlation"])

    def test_register_copies_away_from_shared_catalog(self):
        sentinel = object()
        registry = AlgorithmRegistry()
        registry.register("embeddings", "custom_algo", sentinel)

        self.assertIsNot(registry._algorithms, _BUILTIN_ALGORITHMS)
        self.assertIs(registry.get("embeddings", "custom_algo"), sentinel)
        self.assertNotIn(
            "custom_algo",
            AlgorithmRegistry().list_category("embeddings"),
            "the shared catalog must not see instance registrations",
        )

    def test_unregister_copies_away_from_shared_catalog(self):
        registry = AlgorithmRegistry()
        registry.unregister("embeddings", "node2vec")

        self.assertIsNot(registry._algorithms, _BUILTIN_ALGORITHMS)
        self.assertNotIn("node2vec", registry.list_category("embeddings"))
        self.assertIn(
            "node2vec",
            AlgorithmRegistry().list_category("embeddings"),
            "the shared catalog must keep the built-in",
        )

    def test_clear_category_copies_away_from_shared_catalog(self):
        registry = AlgorithmRegistry()
        registry.clear_category("similarity")

        self.assertEqual(registry.list_category("similarity"), [])
        self.assertEqual(
            len(AlgorithmRegistry().list_category("similarity")), 4,
            "the shared catalog must keep the built-ins",
        )

    def test_clear_all_rebinds_to_fresh_owned_maps(self):
        registry = AlgorithmRegistry()
        registry.clear_all()

        self.assertEqual(registry.list_all(), {c: [] for c in registry.list_all()})
        self.assertIsNot(registry._algorithms, _BUILTIN_ALGORITHMS)
        self.assertEqual(
            len(AlgorithmRegistry().list_category("path_finding")), 3,
            "other instances keep the built-ins",
        )

        registry._register_builtin_algorithms()
        self.assertIs(registry._algorithms, _BUILTIN_ALGORITHMS)
        self.assertEqual(len(registry.list_category("path_finding")), 3)

    def test_get_metadata_returns_a_copy(self):
        registry = AlgorithmRegistry()
        metadata = registry.get_metadata("embeddings", "node2vec")
        self.assertIsNotNone(metadata)
        metadata["description"] = "mutated"

        fresh = registry.get_metadata("embeddings", "node2vec")
        self.assertNotEqual(fresh["description"], "mutated")

    def test_get_capabilities_returns_a_copy(self):
        registry = AlgorithmRegistry()
        capabilities = registry.get_capabilities("embeddings", "node2vec")
        self.assertIsNotNone(capabilities)
        capabilities.append("injected")

        fresh = registry.get_capabilities("embeddings", "node2vec")
        self.assertNotIn("injected", fresh)


if __name__ == "__main__":
    unittest.main()
