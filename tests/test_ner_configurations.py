
import unittest
import sys
import os
from unittest.mock import MagicMock, patch
from dataclasses import asdict

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from semantica.semantic_extract.ner_extractor import NERExtractor, Entity
from semantica.semantic_extract.named_entity_recognizer import NamedEntityRecognizer
from semantica.semantic_extract.methods import get_entity_method

class TestNERConfigurations(unittest.TestCase):
    """
    Test suite to verify NER with different configurations:
    - LLM
    - ML (spaCy)
    - Regex
    - Pattern
    - Fallbacks and Ensemble
    """

    def setUp(self):
        self.text = "Apple Inc. was founded by Steve Jobs."

    @patch('semantica.semantic_extract.methods.create_provider')
    def test_ner_llm_config(self, mock_create_provider):
        """Test NER with LLM configuration"""
        print("\nTesting NER with LLM configuration...")
        
        # Mock LLM provider
        mock_provider = MagicMock()
        mock_provider.is_available.return_value = True
        mock_provider.generate_structured.return_value = [
            {"text": "Apple Inc.", "label": "ORG", "start": 0, "end": 10, "confidence": 0.95},
            {"text": "Steve Jobs", "label": "PERSON", "start": 26, "end": 36, "confidence": 0.98}
        ]
        mock_create_provider.return_value = mock_provider
        
        # Initialize extractor with LLM method
        extractor = NERExtractor(
            method="llm", 
            provider="openai", 
            model="gpt-4",
            temperature=0.1
        )
        
        entities = extractor.extract_entities(self.text)
        
        # Verify provider creation args
        mock_create_provider.assert_called_with("openai", model="gpt-4", temperature=0.1)
        
        # Verify extraction
        self.assertEqual(len(entities), 2)
        self.assertEqual(entities[0].text, "Apple Inc.")
        self.assertEqual(entities[0].label, "ORG")
        self.assertEqual(entities[0].metadata["extraction_method"], "llm")
        self.assertEqual(entities[0].metadata["model"], "gpt-4")

    @patch('semantica.semantic_extract.methods.spacy')
    def test_ner_ml_config_spacy_available(self, mock_spacy):
        """Test NER with ML (spaCy) configuration when spaCy is available"""
        print("\nTesting NER with ML (spaCy) configuration...")
        
        # Mock spaCy nlp model
        mock_nlp = MagicMock()
        mock_doc = MagicMock()
        
        # Mock entities
        ent1 = MagicMock()
        ent1.text = "Apple Inc."
        ent1.label_ = "ORG"
        ent1.start_char = 0
        ent1.end_char = 10
        ent1.confidence = 1.0 # Optional attribute
        
        ent2 = MagicMock()
        ent2.text = "Steve Jobs"
        ent2.label_ = "PERSON"
        ent2.start_char = 26
        ent2.end_char = 36
        ent2.confidence = 0.99
        
        mock_doc.ents = [ent1, ent2]
        mock_nlp.return_value = mock_doc
        mock_spacy.load.return_value = mock_nlp
        
        # Patch SPACY_AVAILABLE in methods module
        with patch('semantica.semantic_extract.methods.SPACY_AVAILABLE', True):
            extractor = NERExtractor(method="ml", model="en_core_web_trf")
            entities = extractor.extract_entities(self.text)
            
            # Verify spacy load called with correct model
            mock_spacy.load.assert_called_with("en_core_web_trf")
            
            self.assertEqual(len(entities), 2)
            self.assertEqual(entities[0].text, "Apple Inc.")
            self.assertEqual(entities[0].label, "ORG")
            self.assertEqual(entities[0].metadata["extraction_method"], "ml")
            self.assertEqual(entities[0].metadata["model"], "en_core_web_trf")

    @patch('semantica.semantic_extract.methods.spacy')
    def test_ner_ml_init_falls_back_when_spacy_runtime_is_broken(self, mock_spacy):
        """Test NER init does not crash when spaCy is installed but unusable at runtime.

        The model load now goes through load_spacy_model() in semantic_extract.methods,
        so we patch methods.spacy (not ner_extractor.spacy) to inject the failure.
        """
        from semantica.semantic_extract.methods import clear_spacy_model_cache
        clear_spacy_model_cache()
        mock_spacy.load.side_effect = RuntimeError("ConfigSchemaNlp is not fully defined")

        with patch('semantica.semantic_extract.ner_extractor.SPACY_AVAILABLE', True):
            extractor = NERExtractor(method="ml", model="en_core_web_sm")

        self.assertIsNone(extractor.nlp)
        self.assertFalse(extractor._ml_runtime_usable)

    @patch('semantica.semantic_extract.methods.get_entity_method')
    @patch('semantica.semantic_extract.methods.spacy')
    def test_ner_ml_runtime_failure_disables_repeated_ml_load_attempts(
        self,
        mock_methods_spacy,
        mock_get_method,
    ):
        """Test degraded ML mode skips repeated spaCy load attempts after init failure.

        The model load at construction time now goes through load_spacy_model() in
        semantic_extract.methods, so methods.spacy is the single mock target for the
        init-time failure.  After the RuntimeError is raised, _ml_runtime_usable is
        False and no further spacy.load (or extract_entities_ml) calls are made.
        """
        from semantica.semantic_extract.methods import clear_spacy_model_cache
        clear_spacy_model_cache()
        mock_methods_spacy.load.side_effect = RuntimeError("ConfigSchemaNlp is not fully defined")
        mock_ml_method = MagicMock(return_value=[])
        mock_get_method.side_effect = lambda name: mock_ml_method if name == "ml" else (lambda *_args, **_kwargs: [])

        with patch('semantica.semantic_extract.ner_extractor.SPACY_AVAILABLE', True):
            extractor = NERExtractor(method=["ml", "pattern"], model="en_core_web_sm")

        entities = extractor.extract_entities(self.text)

        self.assertFalse(extractor._ml_runtime_usable)
        # methods.spacy.load called once during __init__ (the RuntimeError); not again
        # during extract_entities because _filter_unusable_methods removes "ml".
        self.assertEqual(mock_methods_spacy.load.call_count, 1)
        self.assertEqual(mock_ml_method.call_count, 0)
        self.assertIsInstance(entities, list)

    def test_ner_regex_config(self):
        """Test NER with Regex configuration"""
        print("\nTesting NER with Regex configuration...")
        
        custom_patterns = {
            "COMPANY": r"Apple Inc\.",
            "FOUNDER": r"Steve Jobs"
        }
        
        extractor = NERExtractor(method="regex", patterns=custom_patterns)
        entities = extractor.extract_entities(self.text)
        
        self.assertEqual(len(entities), 2)
        
        # Check if labels match custom keys
        labels = sorted([e.label for e in entities])
        self.assertEqual(labels, ["COMPANY", "FOUNDER"])
        
        # Check metadata
        self.assertEqual(entities[0].metadata["extraction_method"], "regex")

    def test_ner_pattern_config(self):
        """Test NER with default Pattern configuration"""
        print("\nTesting NER with Pattern configuration...")
        
        # Default patterns in methods.py match "Apple Inc" (ORG) and "Steve Jobs" (PERSON)
        # Note: The pattern for ORG in methods.py expects "Inc|Corp..."
        
        extractor = NERExtractor(method="pattern")
        entities = extractor.extract_entities(self.text)
        
        self.assertTrue(len(entities) >= 2)
        texts = [e.text for e in entities]
        self.assertIn("Apple Inc", texts) # Regex pattern does not capture the trailing dot
        # Actually methods.py regex: r"\b([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*\s+(?:Inc|Corp|LLC|Ltd|Company))\b"
        # "Apple Inc." -> "Apple Inc" (dot is outside \b if not matched?)
        # Let's check the result strictly
        
    @patch('semantica.semantic_extract.methods.create_provider')
    @patch('semantica.semantic_extract.methods.spacy')
    def test_ner_ensemble_config(self, mock_spacy, mock_create_provider):
        """Test NER with Ensemble (Multiple Methods)"""
        print("\nTesting NER with Ensemble configuration...")
        
        # Setup mocks
        # LLM returns 1 entity
        mock_provider = MagicMock()
        mock_provider.is_available.return_value = True
        mock_provider.generate_structured.return_value = [
             {"text": "Apple Inc.", "label": "ORG", "start": 0, "end": 10, "confidence": 0.95}
        ]
        mock_create_provider.return_value = mock_provider
        
        # ML returns 2 entities
        mock_nlp = MagicMock()
        mock_doc = MagicMock()
        ent1 = MagicMock()
        ent1.text = "Apple Inc."
        ent1.label_ = "ORG"
        ent1.start_char = 0
        ent1.end_char = 10
        ent1.confidence = 0.95
        ent2 = MagicMock()
        ent2.text = "Steve Jobs"
        ent2.label_ = "PERSON"
        ent2.start_char = 26
        ent2.end_char = 36
        ent2.confidence = 0.99
        mock_doc.ents = [ent1, ent2]
        mock_nlp.return_value = mock_doc
        mock_spacy.load.return_value = mock_nlp
        
        with patch('semantica.semantic_extract.methods.SPACY_AVAILABLE', True):
            # Init extractor with list of methods
            extractor = NERExtractor(method=["llm", "ml"], ensemble_voting=True)
            entities = extractor.extract_entities(self.text)
            
            # Since ensemble_voting=True (implied merge), we expect unique entities
            # Apple Inc (from both) + Steve Jobs (from ML)
            
            texts = [e.text for e in entities]
            self.assertIn("Apple Inc.", texts)
            self.assertIn("Steve Jobs", texts)

    @patch('semantica.semantic_extract.methods.HuggingFaceModelLoader')
    def test_ner_huggingface_config(self, mock_loader_cls):
        """Test NER with HuggingFace configuration"""
        print("\nTesting NER with HuggingFace configuration...")
        
        mock_loader = MagicMock()
        mock_loader_cls.return_value = mock_loader
        
        # Mock extract_entities return
        # HuggingFace loader typically returns list of dicts or objects
        mock_loader.extract_entities.return_value = [
            {"word": "Apple Inc.", "entity_group": "ORG", "score": 0.99, "start": 0, "end": 10}
        ]
        
        extractor = NERExtractor(
            method="huggingface", 
            huggingface_model="dslim/bert-base-NER",
            device="cpu"
        )
        entities = extractor.extract_entities(self.text)
        
        mock_loader.load_ner_model.assert_called_with("dslim/bert-base-NER")
        self.assertEqual(len(entities), 1)
        self.assertEqual(entities[0].text, "Apple Inc.")
        self.assertEqual(entities[0].label, "ORG")

if __name__ == '__main__':
    unittest.main()
