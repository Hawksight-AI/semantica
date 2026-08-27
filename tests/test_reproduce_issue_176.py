
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
        self.assertEqual(kwargs["max_tokens"], 128000)


class TestCacheKeyIncludesGenerationParams(unittest.TestCase):
    """Regression tests for the cache-key bug: two calls with identical extraction
    inputs but different generation settings must NOT share a cached result.

    Before the fix, extract_relations_llm (and entities/triplets) built
    cache_params without generation kwargs, so max_tokens=4096 and
    max_tokens=128000 hashed to the same key. The second call would return the
    first cached result without ever running generate_typed again.
    """

    def _make_mock_llm(self, relations=None, entities=None, triplets=None):
        mock_llm = MagicMock()
        mock_llm.is_available.return_value = True
        resp = MagicMock()
        resp.relations = relations if relations is not None else []
        resp.entities = entities if entities is not None else []
        resp.triplets = triplets if triplets is not None else []
        mock_llm.generate_typed.return_value = resp
        return mock_llm

    @patch("semantica.semantic_extract.methods.create_provider")
    def test_relations_different_max_tokens_bypass_cache(self, mock_create_provider):
        """Two relation extraction calls with the same text/entities but different
        max_tokens must each call generate_typed (2 calls total), not reuse the
        first cached result."""
        from semantica.semantic_extract.methods import _result_cache
        _result_cache.clear("relations")

        mock_llm = self._make_mock_llm()
        mock_create_provider.return_value = mock_llm

        entities = [Entity(text="Foo", label="ORG", start_char=0, end_char=3)]

        extract_relations_llm(
            text="some text", entities=entities,
            provider="openai", model="gpt-4", max_tokens=4096
        )
        extract_relations_llm(
            text="some text", entities=entities,
            provider="openai", model="gpt-4", max_tokens=128000
        )

        # generate_typed must have been called twice — once per unique key
        self.assertEqual(
            mock_llm.generate_typed.call_count, 2,
            "Different max_tokens values must produce different cache keys; "
            "second call must not reuse the first cached result."
        )

    @patch("semantica.semantic_extract.methods.create_provider")
    def test_relations_same_max_tokens_uses_cache(self, mock_create_provider):
        """Two identical calls must reuse the cache (generate_typed called once)."""
        from semantica.semantic_extract.methods import _result_cache
        _result_cache.clear("relations")

        mock_llm = self._make_mock_llm()
        mock_create_provider.return_value = mock_llm

        entities = [Entity(text="Foo", label="ORG", start_char=0, end_char=3)]

        extract_relations_llm(
            text="some text", entities=entities,
            provider="openai", model="gpt-4", max_tokens=4096
        )
        extract_relations_llm(
            text="some text", entities=entities,
            provider="openai", model="gpt-4", max_tokens=4096
        )

        self.assertEqual(
            mock_llm.generate_typed.call_count, 1,
            "Identical calls must reuse the cache."
        )

    @patch("semantica.semantic_extract.methods.create_provider")
    def test_relations_different_temperature_bypass_cache(self, mock_create_provider):
        """Different temperature values must also produce different cache keys."""
        from semantica.semantic_extract.methods import _result_cache
        _result_cache.clear("relations")

        mock_llm = self._make_mock_llm()
        mock_create_provider.return_value = mock_llm

        entities = [Entity(text="Bar", label="PERSON", start_char=0, end_char=3)]

        extract_relations_llm(
            text="other text", entities=entities,
            provider="openai", model="gpt-4", temperature=0.0
        )
        extract_relations_llm(
            text="other text", entities=entities,
            provider="openai", model="gpt-4", temperature=1.0
        )

        self.assertEqual(mock_llm.generate_typed.call_count, 2)

    @patch("semantica.semantic_extract.methods.create_provider")
    def test_entities_different_max_tokens_bypass_cache(self, mock_create_provider):
        """extract_entities_llm: different max_tokens must bypass cache."""
        from semantica.semantic_extract.methods import _result_cache
        _result_cache.clear("entities")

        mock_llm = self._make_mock_llm()
        mock_create_provider.return_value = mock_llm

        extract_entities_llm(
            text="some entity text", provider="openai", model="gpt-4",
            max_tokens=4096
        )
        extract_entities_llm(
            text="some entity text", provider="openai", model="gpt-4",
            max_tokens=128000
        )

        self.assertEqual(mock_llm.generate_typed.call_count, 2)

    @patch("semantica.semantic_extract.methods.create_provider")
    def test_triplets_different_max_tokens_bypass_cache(self, mock_create_provider):
        """extract_triplets_llm: different max_tokens must bypass cache."""
        from semantica.semantic_extract.methods import _result_cache
        _result_cache.clear("triplets")

        mock_llm = self._make_mock_llm()
        mock_create_provider.return_value = mock_llm

        extract_triplets_llm(
            text="some triplet text", provider="openai", model="gpt-4",
            max_tokens=4096
        )
        extract_triplets_llm(
            text="some triplet text", provider="openai", model="gpt-4",
            max_tokens=128000
        )

        self.assertEqual(mock_llm.generate_typed.call_count, 2)


class TestCacheKeyIncludesProviderSpecificGenerationParams(unittest.TestCase):
    """Regression tests for provider-specific generation params that aren't part
    of the common OpenAI-shaped kwargs (max_tokens, temperature, etc.) but still
    change provider output and must therefore also change the cache key.

    See providers.py: AnthropicProvider.generate/generate_structured read
    'system' and 'stop_sequences' via a manual pass-through loop (not
    _add_if_set); GeminiProvider.generate reads 'candidate_count' and
    'stop_sequences'; OllamaProvider._build_options reads 'repeat_penalty' and
    'num_ctx'/'context_window'.
    """

    def _make_mock_llm(self):
        mock_llm = MagicMock()
        mock_llm.is_available.return_value = True
        resp = MagicMock()
        resp.relations = []
        mock_llm.generate_typed.return_value = resp
        return mock_llm

    @patch("semantica.semantic_extract.methods.create_provider")
    def test_relations_different_system_prompt_bypass_cache(self, mock_create_provider):
        """Anthropic 'system' prompt changes output; must not share a cache entry."""
        from semantica.semantic_extract.methods import _result_cache
        _result_cache.clear("relations")

        mock_llm = self._make_mock_llm()
        mock_create_provider.return_value = mock_llm

        entities = [Entity(text="Foo", label="ORG", start_char=0, end_char=3)]

        extract_relations_llm(
            text="some text", entities=entities,
            provider="anthropic", model="claude-3-sonnet-20240229",
            system="Extract only ORG relations."
        )
        extract_relations_llm(
            text="some text", entities=entities,
            provider="anthropic", model="claude-3-sonnet-20240229",
            system="Extract only PERSON relations."
        )

        self.assertEqual(
            mock_llm.generate_typed.call_count, 2,
            "Different 'system' prompts must produce different cache keys."
        )

    @patch("semantica.semantic_extract.methods.create_provider")
    def test_relations_different_stop_sequences_bypass_cache(self, mock_create_provider):
        """Anthropic/Gemini 'stop_sequences' must also be part of the cache key."""
        from semantica.semantic_extract.methods import _result_cache
        _result_cache.clear("relations")

        mock_llm = self._make_mock_llm()
        mock_create_provider.return_value = mock_llm

        entities = [Entity(text="Foo", label="ORG", start_char=0, end_char=3)]

        extract_relations_llm(
            text="some text", entities=entities,
            provider="anthropic", model="claude-3-sonnet-20240229",
            stop_sequences=["\n\n"]
        )
        extract_relations_llm(
            text="some text", entities=entities,
            provider="anthropic", model="claude-3-sonnet-20240229",
            stop_sequences=["STOP"]
        )

        self.assertEqual(mock_llm.generate_typed.call_count, 2)

    @patch("semantica.semantic_extract.methods.create_provider")
    def test_relations_different_repeat_penalty_bypass_cache(self, mock_create_provider):
        """Ollama 'repeat_penalty' must also be part of the cache key."""
        from semantica.semantic_extract.methods import _result_cache
        _result_cache.clear("relations")

        mock_llm = self._make_mock_llm()
        mock_create_provider.return_value = mock_llm

        entities = [Entity(text="Foo", label="ORG", start_char=0, end_char=3)]

        extract_relations_llm(
            text="some text", entities=entities,
            provider="ollama", model="llama2",
            repeat_penalty=1.0
        )
        extract_relations_llm(
            text="some text", entities=entities,
            provider="ollama", model="llama2",
            repeat_penalty=1.5
        )

        self.assertEqual(mock_llm.generate_typed.call_count, 2)


if __name__ == "__main__":
    unittest.main()
