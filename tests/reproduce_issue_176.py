
import unittest
from unittest.mock import MagicMock, patch
from semantica.semantic_extract.methods import extract_relations_llm, extract_entities_llm, extract_triplets_llm
from semantica.semantic_extract.ner_extractor import Entity

class TestMaxTokensPropagation(unittest.TestCase):
    @patch("semantica.semantic_extract.methods.create_provider")
    def test_max_tokens_propagation_relations(self, mock_create_provider):
        """Test that max_tokens is passed to generate_typed in extract_relations_llm."""
        # Setup mock
        mock_llm = MagicMock()
        mock_create_provider.return_value = mock_llm
        mock_llm.is_available.return_value = True
        
        # Setup return value to avoid pydantic validation errors
        mock_response = MagicMock()
        mock_response.relations = []
        mock_llm.generate_typed.return_value = mock_response

        # Create dummy entities
        entities = [Entity(text="Foo", label="ORG", start_char=0, end_char=3)]

        # Call the function with max_tokens
        extract_relations_llm(
            text="some text",
            entities=entities,
            provider="openai",
            model="gpt-4",
            max_tokens=128000
        )

        # Check if generate_typed was called with max_tokens
        args, kwargs = mock_llm.generate_typed.call_args
        
        print(f"Relations Call kwargs: {kwargs}")
        
        self.assertIn("max_tokens", kwargs)
        self.assertEqual(kwargs["max_tokens"], 128000)

    @patch("semantica.semantic_extract.methods.create_provider")
    def test_max_tokens_propagation_entities(self, mock_create_provider):
        """Test that max_tokens is passed to generate_typed in extract_entities_llm."""
        # Setup mock
        mock_llm = MagicMock()
        mock_create_provider.return_value = mock_llm
        mock_llm.is_available.return_value = True
        
        # Setup return value to avoid pydantic validation errors
        mock_response = MagicMock()
        mock_response.entities = []
        mock_llm.generate_typed.return_value = mock_response

        # Call the function with max_tokens
        extract_entities_llm(
            text="some text",
            provider="openai",
            model="gpt-4",
            max_tokens=128000
        )

        # Check if generate_typed was called with max_tokens
        args, kwargs = mock_llm.generate_typed.call_args
        
        print(f"Entities Call kwargs: {kwargs}")
        
        self.assertIn("max_tokens", kwargs)
        self.assertEqual(kwargs["max_tokens"], 128000)

    @patch("semantica.semantic_extract.methods.create_provider")
    def test_max_tokens_propagation_triplets(self, mock_create_provider):
        """Test that max_tokens is passed to generate_typed in extract_triplets_llm."""
        # Setup mock
        mock_llm = MagicMock()
        mock_create_provider.return_value = mock_llm
        mock_llm.is_available.return_value = True
        
        # Setup return value to avoid pydantic validation errors
        mock_response = MagicMock()
        mock_response.triplets = []
        mock_llm.generate_typed.return_value = mock_response

        # Call the function with max_tokens
        extract_triplets_llm(
            text="some text",
            provider="openai",
            model="gpt-4",
            max_tokens=128000
        )

        # Check if generate_typed was called with max_tokens
        args, kwargs = mock_llm.generate_typed.call_args
        
        print(f"Triplets Call kwargs: {kwargs}")
        
        self.assertIn("max_tokens", kwargs)
        self.assertEqual(kWargs["max_tokens"], 128000)

if __name__ == "__main__":
    unittest.main()
