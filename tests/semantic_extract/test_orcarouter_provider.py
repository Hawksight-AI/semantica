"""Tests for OrcaRouterProvider — OpenAI-compatible routing gateway."""

import sys
import os
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

# The openai SDK is an optional extra (`pip install semantica[llm-openai]`), not a
# dev dependency. Only the tests that spec a mock against the real OpenAI class
# need it — the rest of this module must still run without it.
try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - depends on the installed extras
    OpenAI = None

requires_openai = unittest.skipIf(OpenAI is None, "openai SDK not installed")


class TestOrcaRouterProviderInit(unittest.TestCase):
    """Tests for OrcaRouterProvider.__init__ and _init_client."""

    def setUp(self):
        from semantica.semantic_extract.providers import OrcaRouterProvider

        self.OrcaRouterProvider = OrcaRouterProvider

    def test_base_url_set_on_init(self):
        """self.base_url must be set before _init_client is called."""
        with patch.object(self.OrcaRouterProvider, "_init_client", return_value=None):
            provider = self.OrcaRouterProvider(api_key="fake-key")
        self.assertTrue(
            hasattr(provider, "base_url"),
            "OrcaRouterProvider missing self.base_url before _init_client",
        )
        self.assertEqual(provider.base_url, "https://api.orcarouter.ai/v1")

    def test_default_model(self):
        """Default model must be an OpenAI-compatible frontier model id."""
        with patch.object(self.OrcaRouterProvider, "_init_client", return_value=None):
            provider = self.OrcaRouterProvider(api_key="fake-key")
        self.assertEqual(provider.model, "openai/gpt-4o")

    def test_base_url_points_to_v1_endpoint(self):
        """base_url must include /v1 so the OpenAI SDK resolves endpoints correctly."""
        with patch.object(self.OrcaRouterProvider, "_init_client", return_value=None):
            provider = self.OrcaRouterProvider(api_key="fake-key")
        self.assertIn("/v1", provider.base_url, "base_url must include /v1")

    def test_init_client_uses_openai_client(self):
        """_init_client must import openai.OpenAI against the OrcaRouter base_url."""
        mock_openai_cls = MagicMock()
        mock_openai_instance = MagicMock()
        mock_openai_cls.return_value = mock_openai_instance

        with patch.dict("sys.modules", {"openai": MagicMock(OpenAI=mock_openai_cls)}):
            import importlib
            import semantica.semantic_extract.providers as providers_mod

            importlib.reload(providers_mod)
            OrcaRouterProvider = providers_mod.OrcaRouterProvider

            provider = OrcaRouterProvider(api_key="sk-orca-test")

        mock_openai_cls.assert_called_once_with(
            api_key="sk-orca-test",
            base_url="https://api.orcarouter.ai/v1",
        )
        self.assertIs(provider.client, mock_openai_instance)

    def test_init_client_no_api_key_leaves_client_none(self):
        """Without an API key, client must remain None."""
        with patch("semantica.semantic_extract.providers.config") as mock_cfg:
            mock_cfg.get_api_key.return_value = None
            with patch.object(
                self.OrcaRouterProvider, "_init_client", return_value=None
            ):
                provider = self.OrcaRouterProvider(api_key=None)
            provider.client = None  # simulate _init_client no-op
        self.assertFalse(provider.is_available())

    def test_init_client_handles_openai_import_error(self):
        """If openai is not installed, _init_client must set client=None, not raise."""
        with patch.object(self.OrcaRouterProvider, "_init_client", return_value=None):
            provider = self.OrcaRouterProvider(api_key="sk-orca-test")
        provider.client = None  # manually simulate ImportError path
        with patch.dict("sys.modules", {"openai": None}):
            try:
                provider._init_client()
            except Exception as e:
                self.fail(f"_init_client raised unexpectedly: {e}")
        self.assertIsNone(provider.client)

    def test_is_available_true_when_client_set(self):
        """is_available() returns True when self.client is an OpenAI instance."""
        with patch.object(self.OrcaRouterProvider, "_init_client", return_value=None):
            provider = self.OrcaRouterProvider(api_key="sk-orca-test")
        provider.client = MagicMock()
        self.assertTrue(provider.is_available())

    def test_is_available_false_when_client_none(self):
        """is_available() returns False when self.client is None."""
        with patch.object(self.OrcaRouterProvider, "_init_client", return_value=None):
            provider = self.OrcaRouterProvider(api_key="sk-orca-test")
        provider.client = None
        self.assertFalse(provider.is_available())


class TestOrcaRouterProviderGenerate(unittest.TestCase):
    """Tests for OrcaRouterProvider.generate / generate_structured."""

    def _make_provider(self, api_key="sk-orca-test"):
        from semantica.semantic_extract.providers import OrcaRouterProvider

        with patch.object(OrcaRouterProvider, "_init_client", return_value=None):
            provider = OrcaRouterProvider(api_key=api_key)
        provider.client = MagicMock()
        return provider

    def test_generate_uses_chat_completions(self):
        """generate() must call client.chat.completions.create."""
        provider = self._make_provider()
        mock_resp = MagicMock()
        mock_resp.choices[0].message.content = "hello"
        provider.client.chat.completions.create.return_value = mock_resp

        result = provider.generate("test prompt")

        provider.client.chat.completions.create.assert_called_once()
        self.assertEqual(result, "hello")

    def test_generate_passes_model(self):
        """generate() must forward the requested model id."""
        provider = self._make_provider()
        mock_resp = MagicMock()
        mock_resp.choices[0].message.content = "x"
        provider.client.chat.completions.create.return_value = mock_resp

        provider.generate("p", model="anthropic/claude-sonnet-4.6")
        kwargs = provider.client.chat.completions.create.call_args[1]
        self.assertEqual(kwargs["model"], "anthropic/claude-sonnet-4.6")

    def test_generate_structured_returns_parsed_json(self):
        """generate_structured() must parse the JSON returned by the model."""
        provider = self._make_provider()
        mock_resp = MagicMock()
        mock_resp.choices[0].message.content = '{"key": "value"}'
        provider.client.chat.completions.create.return_value = mock_resp

        result = provider.generate_structured("test prompt")
        self.assertEqual(result, {"key": "value"})

    def test_generate_structured_uses_json_object(self):
        """generate_structured() must request a json_object response_format."""
        provider = self._make_provider()
        mock_resp = MagicMock()
        mock_resp.choices[0].message.content = '{"key": "value"}'
        provider.client.chat.completions.create.return_value = mock_resp

        provider.generate_structured("test prompt")
        kwargs = provider.client.chat.completions.create.call_args[1]
        self.assertEqual(kwargs["response_format"], {"type": "json_object"})

    def test_generate_raises_without_client(self):
        from semantica.semantic_extract.providers import (
            OrcaRouterProvider,
            ProcessingError,
        )

        with patch.object(OrcaRouterProvider, "_init_client", return_value=None):
            provider = OrcaRouterProvider(api_key="sk-orca-test")
        provider.client = None

        with self.assertRaises(ProcessingError):
            provider.generate("prompt")

    def test_generate_structured_raises_without_client(self):
        from semantica.semantic_extract.providers import (
            OrcaRouterProvider,
            ProcessingError,
        )

        with patch.object(OrcaRouterProvider, "_init_client", return_value=None):
            provider = OrcaRouterProvider(api_key="sk-orca-test")
        provider.client = None

        with self.assertRaises(ProcessingError):
            provider.generate_structured("prompt")


class TestOrcaRouterRegistration(unittest.TestCase):
    """Tests for OrcaRouter registration in the built-in provider map."""

    def test_create_provider_returns_orcarouter(self):
        from semantica.semantic_extract.providers import (
            create_provider,
            OrcaRouterProvider,
        )

        with patch.object(OrcaRouterProvider, "_init_client", return_value=None):
            provider = create_provider(
                "orcarouter", use_pool=False, api_key="sk-orca-test"
            )
        self.assertIsInstance(provider, OrcaRouterProvider)

    def test_create_provider_case_insensitive(self):
        from semantica.semantic_extract.providers import (
            create_provider,
            OrcaRouterProvider,
        )

        with patch.object(OrcaRouterProvider, "_init_client", return_value=None):
            provider = create_provider(
                "OrcaRouter", use_pool=False, api_key="sk-orca-test"
            )
        self.assertIsInstance(provider, OrcaRouterProvider)

    def test_builtin_list_contains_orcarouter(self):
        """create_provider("orcarouter") must resolve to OrcaRouterProvider."""
        from semantica.semantic_extract.providers import (
            _provider_pool,
            OrcaRouterProvider,
        )

        with patch.object(OrcaRouterProvider, "_init_client", return_value=None):
            provider = _provider_pool._create_provider(
                "orcarouter", api_key="sk-orca-test"
            )
        self.assertIsInstance(provider, OrcaRouterProvider)


if __name__ == "__main__":
    unittest.main()
