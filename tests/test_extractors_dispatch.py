import unittest
from unittest.mock import MagicMock, patch
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# The extractors are imported for real. Mocks are installed per test in setUp
# rather than at module scope: pytest imports every test module during
# collection, so anything assigned into sys.modules here is still in place when
# later test modules are imported, and they bind the mocks into their own
# globals. A tearDownModule cannot undo that — by then collection is finished.
from semantica.semantic_extract.ner_extractor import NERExtractor, Entity  # noqa: E402
from semantica.semantic_extract.relation_extractor import RelationExtractor, Relation  # noqa: E402
from semantica.semantic_extract.triplet_extractor import TripletExtractor  # noqa: E402


class TestExtractorsDispatch(unittest.TestCase):
    def setUp(self):
        # The extractors resolve `from .methods import get_entity_method` lazily
        # inside their methods, so the stand-in only has to be in sys.modules
        # while a test runs. patch.dict removes it again afterwards.
        self.mock_methods = MagicMock()
        patcher = patch.dict(
            sys.modules,
            {"semantica.semantic_extract.methods": self.mock_methods},
        )
        patcher.start()
        self.addCleanup(patcher.stop)

        self.mock_extract_entities_hf = MagicMock()
        self.mock_extract_relations_hf = MagicMock()
        self.mock_extract_triplets_hf = MagicMock()

        self.mock_methods.get_entity_method.return_value = self.mock_extract_entities_hf
        self.mock_methods.get_relation_method.return_value = (
            self.mock_extract_relations_hf
        )
        self.mock_methods.get_triplet_method.return_value = (
            self.mock_extract_triplets_hf
        )
        
        # Configure mocks to return something iterable/valid
        self.mock_extract_entities_hf.return_value = [MagicMock(spec=Entity, confidence=0.9, text="Test Entity")]
        self.mock_extract_relations_hf.return_value = [MagicMock(spec=Relation, confidence=0.9)]
        self.mock_extract_triplets_hf.return_value = [MagicMock(confidence=0.9)]

    def test_ner_extractor_huggingface_dispatch(self):
        print("\nTesting NERExtractor dispatch to HuggingFace...")
        # Initialize with HuggingFace method
        extractor = NERExtractor(method="huggingface")
        
        # Call extract_entities
        text = "Steve Jobs founded Apple."
        # Use a specific model via kwargs
        extractor.extract_entities(text, model="my-custom-ner-model")
        
        # Verify get_entity_method was called with "huggingface"
        self.mock_methods.get_entity_method.assert_called_with("huggingface")
        
        # Verify the extraction function was called with correct model
        # We need to check the call args to see if 'model' was passed correctly
        # The logic we implemented: method_options["model"] = all_options.get("huggingface_model") or all_options.get("model") or self.huggingface_model
        
        call_args = self.mock_extract_entities_hf.call_args
        self.assertIsNotNone(call_args, "extract_entities_huggingface should have been called")
        
        _, kwargs = call_args
        self.assertEqual(kwargs.get("model"), "my-custom-ner-model", "Should use model passed in kwargs")
        
        print("NERExtractor dispatch verified.")

    def test_relation_extractor_huggingface_dispatch(self):
        print("\nTesting RelationExtractor dispatch to HuggingFace...")
        extractor = RelationExtractor(method="huggingface")
        
        text = "Steve Jobs founded Apple."
        entities = [MagicMock(spec=Entity)]
        
        # Call extract_relations with explicit model
        extractor.extract_relations(text, entities, model="my-relation-model")
        
        # Verify dispatch
        self.mock_methods.get_relation_method.assert_called_with("huggingface")
        
        call_args = self.mock_extract_relations_hf.call_args
        self.assertIsNotNone(call_args, "extract_relations_huggingface should have been called")
        
        _, kwargs = call_args
        self.assertEqual(kwargs.get("model"), "my-relation-model", "Should use model passed in kwargs")
        
        print("RelationExtractor dispatch verified.")

    def test_triplet_extractor_huggingface_dispatch(self):
        print("\nTesting TripletExtractor dispatch to HuggingFace...")
        extractor = TripletExtractor(method="huggingface")
        
        text = "Steve Jobs founded Apple."
        
        # Call extract_triplets with explicit model
        extractor.extract_triplets(text, model="my-triplet-model")
        
        # Verify dispatch
        self.mock_methods.get_triplet_method.assert_called_with("huggingface")
        
        call_args = self.mock_extract_triplets_hf.call_args
        self.assertIsNotNone(call_args, "extract_triplets_huggingface should have been called")
        
        _, kwargs = call_args
        self.assertEqual(kwargs.get("model"), "my-triplet-model", "Should use model passed in kwargs")
        
        print("TripletExtractor dispatch verified.")

    def test_ner_extractor_huggingface_fallback(self):
        print("\nTesting NERExtractor fallback logic...")
        # Init with huggingface_model in config
        extractor = NERExtractor(method="huggingface", huggingface_model="config-model")
        
        extractor.extract_entities("text")
        
        _, kwargs = self.mock_extract_entities_hf.call_args
        self.assertEqual(kwargs.get("model"), "config-model", "Should prioritize huggingface_model from config")
        
        # Now override with kwargs model
        extractor.extract_entities("text", model="kwargs-model")
        _, kwargs = self.mock_extract_entities_hf.call_args
        self.assertEqual(kwargs.get("model"), "kwargs-model", "Should allow overriding config huggingface_model via model kwarg")
        
        # Let's test passing 'huggingface_model' in kwargs
        extractor.extract_entities("text", huggingface_model="override-model")
        _, kwargs = self.mock_extract_entities_hf.call_args
        self.assertEqual(kwargs.get("model"), "override-model", "Should allow overriding huggingface_model via kwargs")

    def test_triplet_extractor_lazy_loading(self):
        print("\nTesting TripletExtractor lazy loading for HuggingFace...")
        # Initialize with HuggingFace method
        extractor = TripletExtractor(method="huggingface")
        
        # Check initial state
        self.assertIsNone(extractor._ner_extractor)
        self.assertIsNone(extractor._relation_extractor)
        
        # Run extraction
        extractor.extract_triplets("Steve Jobs founded Apple.")
        
        # Check state AFTER extraction - should STILL be None because huggingface (REBEL) doesn't need them
        self.assertIsNone(extractor._ner_extractor, "NERExtractor should not be initialized for HuggingFace method")
        self.assertIsNone(extractor._relation_extractor, "RelationExtractor should not be initialized for HuggingFace method")
        
        print("TripletExtractor lazy loading verified.")

if __name__ == '__main__':
    unittest.main()
