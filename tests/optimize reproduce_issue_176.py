import unittest
from unittest.mock import MagicMock, patch

from semantica.semantic_extract.methods import (
    extract_entities_llm,
    extract_relations_llm,
    extract_triplets_llm,
)
from semantica.semantic_extract.ner_extractor import Entity


class TestMaxTokensPropagation(unittest.TestCase):
    MAX_TOKENS = 128000

    def setUp(self):
        self.mock_llm = MagicMock()
        self.mock_llm.is_available.return_value = True

    def _assert_max_tokens_propagated(
        self,
        function,
        expected_attribute=None,
        **kwargs,
    ):
        """Verify max_tokens reaches generate_typed()."""
        response = MagicMock()

        if expected_attribute:
            setattr(response, expected_attribute, [])

        self.mock_llm.generate_typed.return_value = response

        function(
            text="some text",
            provider="openai",
            model="gpt-4",
            max_tokens=self.MAX_TOKENS,
            **kwargs,
        )

        self.mock_llm.generate_typed.assert_called_once()

        call_kwargs = self.mock_llm.generate_typed.call_args.kwargs

        self.assertEqual(
            call_kwargs.get("max_tokens"),
            self.MAX_TOKENS,
            "max_tokens was not propagated correctly",
        )

    @patch("semantica.semantic_extract.methods.create_provider")
    def test_max_tokens_propagation_relations(self, mock_create_provider):
        """max_tokens is passed to generate_typed() for relations."""
        mock_create_provider.return_value = self.mock_llm

        entities = [
            Entity(
                text="Foo",
                label="ORG",
                start_char=0,
                end_char=3,
            )
        ]

        self._assert_max_tokens_propagated(
            extract_relations_llm,
            expected_attribute="relations",
            entities=entities,
        )

    @patch("semantica.semantic_extract.methods.create_provider")
    def test_max_tokens_propagation_entities(self, mock_create_provider):
        """max_tokens is passed to generate_typed() for entities."""
        mock_create_provider.return_value = self.mock_llm

        self._assert_max_tokens_propagated(
            extract_entities_llm,
            expected_attribute="entities",
        )

    @patch("semantica.semantic_extract.methods.create_provider")
    def test_max_tokens_propagation_triplets(self, mock_create_provider):
        """max_tokens is passed to generate_typed() for triplets."""
        mock_create_provider.return_value = self.mock_llm

        self._assert_max_tokens_propagated(
            extract_triplets_llm,
            expected_attribute="triplets",
        )


if __name__ == "__main__":
    unittest.main()
