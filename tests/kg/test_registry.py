"""
Test suite for enhanced registry module.

This module tests the AlgorithmRegistry class and its algorithm
registration and discovery capabilities.
"""

import pytest
from unittest.mock import Mock

from semantica.kg.registry import AlgorithmRegistry


class TestAlgorithmRegistry:
    """Test cases for AlgorithmRegistry class."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.registry = AlgorithmRegistry()
        
        # Mock algorithm classes
        self.mock_embedder_class = Mock()
        self.mock_similarity_class = Mock()
        self.mock_path_finder_class = Mock()
    
    def test_init_default(self):
        """Test AlgorithmRegistry initialization."""
        registry = AlgorithmRegistry()
        
        # Should have all categories initialized
        assert "embeddings" in registry._algorithms
        assert "similarity" in registry._algorithms
        assert "path_finding" in registry._algorithms
        assert "link_prediction" in registry._algorithms
        assert "centrality" in registry._algorithms
        assert "community_detection" in registry._algorithms
        
        # Should have built-in algorithms registered
        assert "node2vec" in registry._algorithms["embeddings"]
        assert "cosine" in registry._algorithms["similarity"]
        assert "dijkstra" in registry._algorithms["path_finding"]
        assert "preferential_attachment" in registry._algorithms["link_prediction"]
        assert "pagerank" in registry._algorithms["centrality"]
        assert "label_propagation" in registry._algorithms["community_detection"]
    
    def test_register_algorithm(self):
        """Test registering a new algorithm."""
        self.registry.register(
            "embeddings",
            "custom_algo",
            self.mock_embedder_class,
            metadata={"description": "Custom embedding algorithm"},
            capabilities=["custom_capability"]
        )
        
        assert "custom_algo" in self.registry._algorithms["embeddings"]
        assert self.registry._algorithms["embeddings"]["custom_algo"] == self.mock_embedder_class
        assert self.registry._metadata[("embeddings", "custom_algo")] == {"description": "Custom embedding algorithm"}
        assert self.registry._capabilities[("embeddings", "custom_algo")] == ["custom_capability"]
    
    def test_register_invalid_category(self):
        """Test registering algorithm with invalid category."""
        with pytest.raises(ValueError, match="Unsupported algorithm category"):
            self.registry.register(
                "invalid_category",
                "algo",
                self.mock_embedder_class
            )
    
    def test_register_duplicate_algorithm(self):
        """Test registering duplicate algorithm."""
        with pytest.raises(ValueError, match="Algorithm node2vec already registered"):
            self.registry.register(
                "embeddings",
                "node2vec",
                self.mock_embedder_class
            )
    
    def test_get_algorithm(self):
        """Test getting algorithm class."""
        # Register a custom algorithm
        self.registry.register(
            "embeddings",
            "custom_algo",
            self.mock_embedder_class
        )
        
        # Get existing algorithm
        algo_class = self.registry.get("embeddings", "custom_algo")
        assert algo_class == self.mock_embedder_class
        
        # Get non-existent algorithm
        algo_class = self.registry.get("embeddings", "non_existent")
        assert algo_class is None
    
    def test_create_instance(self):
        """Test creating algorithm instance."""
        # Register a mock algorithm class
        mock_instance = Mock()
        self.mock_embedder_class.return_value = mock_instance
        
        self.registry.register(
            "embeddings",
            "custom_algo",
            self.mock_embedder_class
        )
        
        # Create instance
        instance = self.registry.create_instance(
            "embeddings",
            "custom_algo",
            param1="value1",
            param2="value2"
        )
        
        self.mock_embedder_class.assert_called_once_with(param1="value1", param2="value2")
        assert instance == mock_instance
    
    def test_create_instance_non_existent(self):
        """Test creating instance of non-existent algorithm."""
        with pytest.raises(ValueError, match="Algorithm non_existent not found"):
            self.registry.create_instance("embeddings", "non_existent")
    
    def test_list_category(self):
        """Test listing algorithms in a category."""
        algorithms = self.registry.list_category("embeddings")
        
        assert isinstance(algorithms, list)
        assert "node2vec" in algorithms
        
        # Register a custom algorithm
        self.registry.register(
            "embeddings",
            "custom_algo",
            self.mock_embedder_class
        )
        
        algorithms = self.registry.list_category("embeddings")
        assert "custom_algo" in algorithms
    
    def test_list_all(self):
        """Test listing all algorithms."""
        all_algorithms = self.registry.list_all()
        
        assert isinstance(all_algorithms, dict)
        assert "embeddings" in all_algorithms
        assert "similarity" in all_algorithms
        assert "path_finding" in all_algorithms
        
        # Each category should have algorithms
        for category, algorithms in all_algorithms.items():
            assert isinstance(algorithms, list)
            assert len(algorithms) > 0
    
    def test_get_metadata(self):
        """Test getting algorithm metadata."""
        # Register algorithm with metadata
        metadata = {"description": "Test algorithm", "parameters": ["param1", "param2"]}
        self.registry.register(
            "embeddings",
            "test_algo",
            self.mock_embedder_class,
            metadata=metadata
        )
        
        # Get metadata
        retrieved_metadata = self.registry.get_metadata("embeddings", "test_algo")
        assert retrieved_metadata == metadata
        
        # Get non-existent metadata
        non_existent = self.registry.get_metadata("embeddings", "non_existent")
        assert non_existent is None
    
    def test_get_capabilities(self):
        """Test getting algorithm capabilities."""
        # Register algorithm with capabilities
        capabilities = ["capability1", "capability2"]
        self.registry.register(
            "embeddings",
            "test_algo",
            self.mock_embedder_class,
            capabilities=capabilities
        )
        
        # Get capabilities
        retrieved_capabilities = self.registry.get_capabilities("embeddings", "test_algo")
        assert retrieved_capabilities == capabilities
        
        # Get non-existent capabilities
        non_existent = self.registry.get_capabilities("embeddings", "non_existent")
        assert non_existent is None
    
    def test_unregister(self):
        """Test unregistering an algorithm."""
        # Register a custom algorithm
        self.registry.register(
            "embeddings",
            "custom_algo",
            self.mock_embedder_class,
            metadata={"description": "Custom"},
            capabilities=["cap1"]
        )
        
        # Verify it's registered
        assert "custom_algo" in self.registry._algorithms["embeddings"]
        assert ("embeddings", "custom_algo") in self.registry._metadata
        assert ("embeddings", "custom_algo") in self.registry._capabilities
        
        # Unregister
        self.registry.unregister("embeddings", "custom_algo")
        
        # Verify it's removed
        assert "custom_algo" not in self.registry._algorithms["embeddings"]
        assert ("embeddings", "custom_algo") not in self.registry._metadata
        assert ("embeddings", "custom_algo") not in self.registry._capabilities
    
    def test_clear_category(self):
        """Test clearing all algorithms in a category."""
        # Register custom algorithms
        self.registry.register("embeddings", "algo1", self.mock_embedder_class)
        self.registry.register("embeddings", "algo2", self.mock_similarity_class)
        
        # Verify algorithms exist
        assert len(self.registry._algorithms["embeddings"]) > 2  # Built-in + custom
        
        # Clear category
        self.registry.clear_category("embeddings")
        
        # Verify category is empty
        assert len(self.registry._algorithms["embeddings"]) == 0
        
        # Verify metadata and capabilities are cleared
        embedding_keys = [key for key in self.registry._metadata.keys() if key[0] == "embeddings"]
        assert len(embedding_keys) == 0
    
    def test_clear_all(self):
        """Test clearing all algorithms."""
        # Register custom algorithms in multiple categories
        self.registry.register("embeddings", "algo1", self.mock_embedder_class)
        self.registry.register("similarity", "algo2", self.mock_similarity_class)
        
        # Verify algorithms exist
        assert len(self.registry._algorithms["embeddings"]) > 1
        assert len(self.registry._algorithms["similarity"]) > 1
        
        # Clear all
        self.registry.clear_all()
        
        # Verify all categories are empty
        for category in self.registry._algorithms:
            assert len(self.registry._algorithms[category]) == 0
        
        # Verify metadata and capabilities are cleared
        assert len(self.registry._metadata) == 0
        assert len(self.registry._capabilities) == 0


class TestAlgorithmRegistryBuiltinAlgorithms:
    """Test built-in algorithm registration."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.registry = AlgorithmRegistry()
    
    def test_builtin_embeddings(self):
        """Test built-in embedding algorithms."""
        algorithms = self.registry.list_category("embeddings")
        assert "node2vec" in algorithms
        
        metadata = self.registry.get_metadata("embeddings", "node2vec")
        assert metadata is not None
        assert "description" in metadata
        assert "parameters" in metadata
        assert "complexity" in metadata
        assert "quality" in metadata
        assert "use_case" in metadata
        
        capabilities = self.registry.get_capabilities("embeddings", "node2vec")
        assert capabilities is not None
        assert "biased_random_walks" in capabilities
        assert "word2vec_training" in capabilities
        assert "embedding_storage" in capabilities
    
    def test_builtin_similarity(self):
        """Test built-in similarity algorithms."""
        algorithms = self.registry.list_category("similarity")
        expected_metrics = ["cosine", "euclidean", "manhattan", "correlation"]
        
        for metric in expected_metrics:
            assert metric in algorithms
            
            metadata = self.registry.get_metadata("similarity", metric)
            assert metadata is not None
            assert "description" in metadata
            assert "parameters" in metadata
            assert "complexity" in metadata
            assert "quality" in metadata
            assert "use_case" in metadata
            
            capabilities = self.registry.get_capabilities("similarity", metric)
            assert capabilities is not None
            assert "vector_similarity" in capabilities
            assert "batch_computation" in capabilities
    
    def test_builtin_path_finding(self):
        """Test built-in path finding algorithms."""
        algorithms = self.registry.list_category("path_finding")
        expected_algorithms = ["dijkstra", "astar", "bfs"]
        
        for algo in expected_algorithms:
            assert algo in algorithms
            
            metadata = self.registry.get_metadata("path_finding", algo)
            assert metadata is not None
            assert "description" in metadata
            assert "parameters" in metadata
            assert "complexity" in metadata
            assert "quality" in metadata
            assert "use_case" in metadata
            
            capabilities = self.registry.get_capabilities("path_finding", algo)
            assert capabilities is not None
            assert "shortest_path" in capabilities
            assert "path_reconstruction" in capabilities
    
    def test_builtin_link_prediction(self):
        """Test built-in link prediction algorithms."""
        algorithms = self.registry.list_category("link_prediction")
        expected_algorithms = [
            "preferential_attachment", "common_neighbors", 
            "jaccard_coefficient", "adamic_adar"
        ]
        
        for algo in expected_algorithms:
            assert algo in algorithms
            
            metadata = self.registry.get_metadata("link_prediction", algo)
            assert metadata is not None
            assert "description" in metadata
            assert "parameters" in metadata
            assert "complexity" in metadata
            assert "quality" in metadata
            assert "use_case" in metadata
            
            capabilities = self.registry.get_capabilities("link_prediction", algo)
            assert capabilities is not None
            assert "neighbor_analysis" in capabilities
            assert "similarity_scoring" in capabilities
    
    def test_builtin_centrality(self):
        """Test built-in centrality algorithms."""
        algorithms = self.registry.list_category("centrality")
        assert "pagerank" in algorithms
        
        metadata = self.registry.get_metadata("centrality", "pagerank")
        assert metadata is not None
        assert "description" in metadata
        assert "parameters" in metadata
        assert "complexity" in metadata
        assert "quality" in metadata
        assert "use_case" in metadata
        
        capabilities = self.registry.get_capabilities("centrality", "pagerank")
        assert capabilities is not None
        assert "iterative_computation" in capabilities
        assert "convergence_detection" in capabilities
    
    def test_builtin_community_detection(self):
        """Test built-in community detection algorithms."""
        algorithms = self.registry.list_category("community_detection")
        assert "label_propagation" in algorithms
        
        metadata = self.registry.get_metadata("community_detection", "label_propagation")
        assert metadata is not None
        assert "description" in metadata
        assert "parameters" in metadata
        assert "complexity" in metadata
        assert "quality" in metadata
        assert "use_case" in metadata
        
        capabilities = self.registry.get_capabilities("community_detection", "label_propagation")
        assert capabilities is not None
        assert "iterative_labeling" in capabilities
        assert "convergence_detection" in capabilities


class TestAlgorithmRegistryExtensibility:
    """Test AlgorithmRegistry extensibility features."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.registry = AlgorithmRegistry()
    
    def test_custom_algorithm_registration(self):
        """Test registering custom algorithms with full metadata."""
        # Define a custom algorithm class
        class CustomEmbedding:
            def __init__(self, dimension=128):
                self.dimension = dimension
        
        # Register with comprehensive metadata
        metadata = {
            "description": "Custom embedding algorithm for testing",
            "parameters": ["dimension", "learning_rate"],
            "complexity": "O(V * E)",
            "quality": "High",
            "use_case": "Custom embedding tasks",
            "author": "Test Author",
            "version": "1.0.0"
        }
        
        capabilities = [
            "custom_feature1",
            "custom_feature2",
            "scalable_computation"
        ]
        
        self.registry.register(
            "embeddings",
            "custom_test",
            CustomEmbedding,
            metadata=metadata,
            capabilities=capabilities
        )
        
        # Verify registration
        assert self.registry.get("embeddings", "custom_test") == CustomEmbedding
        
        # Verify metadata
        retrieved_metadata = self.registry.get_metadata("embeddings", "custom_test")
        assert retrieved_metadata == metadata
        
        # Verify capabilities
        retrieved_capabilities = self.registry.get_capabilities("embeddings", "custom_test")
        assert retrieved_capabilities == capabilities
    
    def test_algorithm_instance_creation_with_params(self):
        """Test creating algorithm instances with custom parameters."""
        class TestAlgorithm:
            def __init__(self, param1=None, param2=None):
                self.param1 = param1
                self.param2 = param2
        
        self.registry.register("similarity", "test_algo", TestAlgorithm)
        
        # Create instance with parameters
        instance = self.registry.create_instance(
            "similarity",
            "test_algo",
            param1="value1",
            param2="value2"
        )
        
        assert isinstance(instance, TestAlgorithm)
        assert instance.param1 == "value1"
        assert instance.param2 == "value2"
    
    def test_algorithm_discovery_by_capabilities(self):
        """Test discovering algorithms by capabilities."""
        # Register algorithms with different capabilities
        self.registry.register(
            "embeddings",
            "algo1",
            Mock(),
            capabilities=["fast", "scalable"]
        )
        self.registry.register(
            "embeddings",
            "algo2",
            Mock(),
            capabilities=["accurate", "memory_efficient"]
        )
        self.registry.register(
            "embeddings",
            "algo3",
            Mock(),
            capabilities=["fast", "accurate"]
        )
        
        # Discover algorithms with specific capabilities
        all_algorithms = self.registry.list_all()
        embedding_algorithms = all_algorithms["embeddings"]
        
        # Should include our custom algorithms
        assert "algo1" in embedding_algorithms
        assert "algo2" in embedding_algorithms
        assert "algo3" in embedding_algorithms
        
        # Check capabilities
        assert "fast" in self.registry.get_capabilities("embeddings", "algo1")
        assert "scalable" in self.registry.get_capabilities("embeddings", "algo1")
        assert "accurate" in self.registry.get_capabilities("embeddings", "algo2")
        assert "memory_efficient" in self.registry.get_capabilities("embeddings", "algo2")
    
    def test_algorithm_metadata_querying(self):
        """Test querying algorithms by metadata."""
        # Register algorithms with different metadata
        metadata1 = {
            "description": "Fast algorithm",
            "complexity": "O(V)",
            "quality": "Medium"
        }
        
        metadata2 = {
            "description": "Accurate algorithm",
            "complexity": "O(V^2)",
            "quality": "High"
        }
        
        self.registry.register("path_finding", "fast_algo", Mock(), metadata=metadata1)
        self.registry.register("path_finding", "accurate_algo", Mock(), metadata=metadata2)
        
        # Query metadata
        fast_metadata = self.registry.get_metadata("path_finding", "fast_algo")
        accurate_metadata = self.registry.get_metadata("path_finding", "accurate_algo")
        
        assert fast_metadata["complexity"] == "O(V)"
        assert accurate_metadata["complexity"] == "O(V^2)"
        assert fast_metadata["quality"] == "Medium"
        assert accurate_metadata["quality"] == "High"


class TestAlgorithmRegistryErrorHandling:
    """Test error handling in AlgorithmRegistry."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.registry = AlgorithmRegistry()
    
    def test_register_none_algorithm_class(self):
        """Test registering None as algorithm class."""
        # This should work (built-in algorithms use None)
        self.registry.register("embeddings", "test_none", None, metadata={"test": "value"})
        
        # Should be able to register but not create instances
        assert "test_none" in self.registry._algorithms["embeddings"]
        
        # Creating instance should fail
        with pytest.raises(TypeError):
            self.registry.create_instance("embeddings", "test_none")
    
    def test_get_non_existent_category(self):
        """Test getting algorithms from non-existent category."""
        algorithms = self.registry.list_category("non_existent_category")
        assert algorithms == []
    
    def test_unregister_non_existent_algorithm(self):
        """Test unregistering non-existent algorithm."""
        # Should not raise error
        self.registry.unregister("embeddings", "non_existent")
        # Should just do nothing
    
    def test_clear_non_existent_category(self):
        """Test clearing non-existent category."""
        # Should not raise error
        self.registry.clear_category("non_existent_category")
        # Should just do nothing


class TestAlgorithmRegistrySharedCatalog:
    """Tests for the shared, copy-on-write built-in catalog."""

    def test_init_binds_shared_catalog(self):
        """A new registry shares the module catalog and owns nothing yet."""
        from semantica.kg.registry import (
            _BUILTIN_ALGORITHMS,
            _BUILTIN_CAPABILITIES,
            _BUILTIN_METADATA,
        )

        registry = AlgorithmRegistry()

        assert registry._owns_catalog is False
        assert registry._algorithms is _BUILTIN_ALGORITHMS
        assert registry._metadata is _BUILTIN_METADATA
        assert registry._capabilities is _BUILTIN_CAPABILITIES

    def test_init_does_not_register_builtins_per_instance(self, monkeypatch):
        """Construction must not replay register() for the built-ins."""
        calls = []
        monkeypatch.setattr(
            AlgorithmRegistry,
            "register",
            lambda self, *args, **kwargs: calls.append(args),
        )

        AlgorithmRegistry()

        assert calls == []

    def test_register_does_not_leak_into_other_instances(self):
        """Registering on one instance must not affect others or the module."""
        from semantica.kg.registry import _BUILTIN_ALGORITHMS, algorithm_registry

        r1 = AlgorithmRegistry()
        r2 = AlgorithmRegistry()

        r1.register("embeddings", "iso_algo", None, metadata={"k": "v"})

        assert "iso_algo" in r1.list_category("embeddings")
        assert "iso_algo" not in r2.list_category("embeddings")
        assert "iso_algo" not in algorithm_registry.list_category("embeddings")
        assert "iso_algo" not in _BUILTIN_ALGORITHMS["embeddings"]
        assert r1._owns_catalog is True
        assert r2._owns_catalog is False

    def test_unregister_does_not_leak_into_other_instances(self):
        """Unregistering a built-in on one instance must not affect others."""
        from semantica.kg.registry import _BUILTIN_ALGORITHMS

        r1 = AlgorithmRegistry()
        r2 = AlgorithmRegistry()

        r1.unregister("embeddings", "node2vec")

        assert "node2vec" not in r1.list_category("embeddings")
        assert "node2vec" in r2.list_category("embeddings")
        assert "node2vec" in _BUILTIN_ALGORITHMS["embeddings"]

    def test_get_metadata_returns_a_copy(self):
        """Mutating returned metadata must not leak into the shared catalog."""
        from semantica.kg.registry import _BUILTIN_METADATA

        r1 = AlgorithmRegistry()
        params = r1.get_metadata("embeddings", "node2vec")["parameters"]
        params.append("LEAK")

        r2 = AlgorithmRegistry()
        assert "LEAK" not in r2.get_metadata("embeddings", "node2vec")["parameters"]
        assert "LEAK" not in _BUILTIN_METADATA[("embeddings", "node2vec")]["parameters"]

    def test_register_builtin_algorithms_rebinds_shared_catalog(self):
        """After clear_all, _register_builtin_algorithms rebinds the shared maps."""
        from semantica.kg.registry import _BUILTIN_ALGORITHMS

        registry = AlgorithmRegistry()
        registry.clear_all()
        assert registry.list_category("embeddings") == []
        assert registry._owns_catalog is True

        registry._register_builtin_algorithms()

        assert "node2vec" in registry.list_category("embeddings")
        assert registry._owns_catalog is False
        assert registry._algorithms is _BUILTIN_ALGORITHMS

    def test_get_capabilities_returns_a_copy(self):
        """Mutating returned capabilities must not leak into the shared catalog."""
        from semantica.kg.registry import _BUILTIN_CAPABILITIES

        r1 = AlgorithmRegistry()
        caps = r1.get_capabilities("embeddings", "node2vec")
        caps.append("LEAK")

        r2 = AlgorithmRegistry()
        assert "LEAK" not in r2.get_capabilities("embeddings", "node2vec")
        assert "LEAK" not in _BUILTIN_CAPABILITIES[("embeddings", "node2vec")]

    def test_clear_category_does_not_leak_into_other_instances(self):
        """clear_category on one instance must not affect others or the module."""
        from semantica.kg.registry import _BUILTIN_ALGORITHMS

        r1 = AlgorithmRegistry()
        r2 = AlgorithmRegistry()

        r1.clear_category("embeddings")

        assert r1.list_category("embeddings") == []
        assert "node2vec" in r2.list_category("embeddings")
        assert "node2vec" in _BUILTIN_ALGORITHMS["embeddings"]
        assert r2._owns_catalog is False

    def test_shared_builtin_catalog_is_read_only(self):
        """The shared module maps reject in-place mutation."""
        import pytest

        from semantica.kg.registry import (
            _BUILTIN_ALGORITHMS,
            _BUILTIN_CAPABILITIES,
            _BUILTIN_METADATA,
        )

        with pytest.raises(TypeError):
            _BUILTIN_METADATA[("embeddings", "node2vec")] = {}
        with pytest.raises(TypeError):
            _BUILTIN_CAPABILITIES[("embeddings", "node2vec")] = []
        with pytest.raises(TypeError):
            _BUILTIN_ALGORITHMS["embeddings"]["x"] = None


if __name__ == "__main__":
    pytest.main([__file__])
