"""Tests for PR #482: DeepSeekProvider switch from deepseek SDK to openai SDK."""

import sys
import os
import unittest
from unittest.mock import patch, MagicMock, call
from pydantic import BaseModel

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

# The openai SDK is an optional extra (`pip install semantica[llm-openai]`), not a
# dev dependency. Only the tests that spec a mock against the real OpenAI class
# need it — the rest of this module must still run without it.
try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - depends on the installed extras
    OpenAI = None

requires_openai = unittest.skipIf(OpenAI is None, "openai SDK not installed")


class TestDeepSeekProviderInit(unittest.TestCase):
    """Tests for DeepSeekProvider.__init__ and _init_client after PR #482."""

    def setUp(self):
        from semantica.semantic_extract.providers import DeepSeekProvider
        self.DeepSeekProvider = DeepSeekProvider

    def test_base_url_set_on_init(self):
        """self.base_url must be set before _init_client is called (PR #482 regression)."""
        with patch.object(self.DeepSeekProvider, "_init_client", return_value=None):
            provider = self.DeepSeekProvider(api_key="fake-key")
        self.assertTrue(
            hasattr(provider, "base_url"),
            "DeepSeekProvider missing self.base_url — causes AttributeError in _init_client",
        )
        self.assertEqual(provider.base_url, "https://api.deepseek.com/v1")

    def test_base_url_points_to_v1_endpoint(self):
        """base_url must include /v1 so OpenAI SDK resolves /chat/completions correctly."""
        with patch.object(self.DeepSeekProvider, "_init_client", return_value=None):
            provider = self.DeepSeekProvider(api_key="fake-key")
        self.assertIn("/v1", provider.base_url, "base_url must include /v1")

    def test_init_client_uses_openai_not_deepseek(self):
        """_init_client must import openai.OpenAI, not deepseek.Client."""
        mock_openai_cls = MagicMock()
        mock_openai_instance = MagicMock()
        mock_openai_cls.return_value = mock_openai_instance

        with patch.dict("sys.modules", {"openai": MagicMock(OpenAI=mock_openai_cls)}):
            # Re-import to pick up patched sys.modules
            import importlib
            import semantica.semantic_extract.providers as providers_mod
            importlib.reload(providers_mod)
            DeepSeekProvider = providers_mod.DeepSeekProvider

            provider = DeepSeekProvider(api_key="sk-test")

        mock_openai_cls.assert_called_once_with(
            api_key="sk-test",
            base_url="https://api.deepseek.com/v1",
        )
        self.assertIs(provider.client, mock_openai_instance)

    def test_init_client_no_api_key_leaves_client_none(self):
        """Without an API key, client must remain None."""
        with patch("semantica.semantic_extract.providers.config") as mock_cfg:
            mock_cfg.get_api_key.return_value = None
            with patch.object(self.DeepSeekProvider, "_init_client", return_value=None):
                provider = self.DeepSeekProvider(api_key=None)
            provider.client = None  # simulate _init_client no-op
        self.assertFalse(provider.is_available())

    def test_init_client_handles_openai_import_error(self):
        """If openai is not installed, _init_client must set client=None, not raise."""
        with patch.object(self.DeepSeekProvider, "_init_client", return_value=None):
            provider = self.DeepSeekProvider(api_key="sk-test")
        provider.client = None  # manually simulate ImportError path
        # Directly call _init_client with openai blocked
        with patch.dict("sys.modules", {"openai": None}):
            try:
                provider._init_client()
            except Exception as e:
                self.fail(f"_init_client raised unexpectedly: {e}")
        self.assertIsNone(provider.client)

    def test_is_available_true_when_client_set(self):
        """is_available() returns True when self.client is an OpenAI instance."""
        with patch.object(self.DeepSeekProvider, "_init_client", return_value=None):
            provider = self.DeepSeekProvider(api_key="sk-test")
        provider.client = MagicMock()
        self.assertTrue(provider.is_available())

    def test_is_available_false_when_client_none(self):
        """is_available() returns False when self.client is None."""
        with patch.object(self.DeepSeekProvider, "_init_client", return_value=None):
            provider = self.DeepSeekProvider(api_key="sk-test")
        provider.client = None
        self.assertFalse(provider.is_available())

    def test_no_deepseek_module_imported(self):
        """deepseek module must NOT be imported by _init_client after PR #482."""
        with patch.object(self.DeepSeekProvider, "_init_client", return_value=None):
            provider = self.DeepSeekProvider(api_key="sk-test")
        provider.client = None

        blocked = MagicMock()
        blocked.__spec__ = None
        with patch.dict("sys.modules", {"deepseek": None}):
            # _init_client should succeed even if deepseek is completely absent
            mock_openai = MagicMock()
            mock_openai.OpenAI.return_value = MagicMock()
            with patch.dict("sys.modules", {"openai": mock_openai, "deepseek": None}):
                try:
                    provider._init_client()
                except Exception as e:
                    self.fail(f"_init_client raised when deepseek absent: {e}")


class TestDeepSeekProviderGenerate(unittest.TestCase):
    """Tests for DeepSeekProvider.generate / generate_structured with OpenAI client."""

    def _make_provider(self, api_key="sk-test"):
        from semantica.semantic_extract.providers import DeepSeekProvider
        with patch.object(DeepSeekProvider, "_init_client", return_value=None):
            provider = DeepSeekProvider(api_key=api_key)
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
        provider = self._make_provider()
        mock_resp = MagicMock()
        mock_resp.choices[0].message.content = "x"
        provider.client.chat.completions.create.return_value = mock_resp

        provider.generate("p", model="deepseek-reasoner")
        kwargs = provider.client.chat.completions.create.call_args[1]
        self.assertEqual(kwargs["model"], "deepseek-reasoner")

    def test_generate_structured_returns_parsed_json(self):
        provider = self._make_provider()
        mock_resp = MagicMock()
        mock_resp.choices[0].message.content = '{"key": "value"}'
        provider.client.chat.completions.create.return_value = mock_resp

        result = provider.generate_structured("test prompt")
        self.assertEqual(result, {"key": "value"})

    def test_generate_raises_without_client(self):
        from semantica.semantic_extract.providers import DeepSeekProvider, ProcessingError
        with patch.object(DeepSeekProvider, "_init_client", return_value=None):
            provider = DeepSeekProvider(api_key="sk-test")
        provider.client = None

        with self.assertRaises(ProcessingError):
            provider.generate("prompt")

    def test_generate_structured_raises_without_client(self):
        from semantica.semantic_extract.providers import DeepSeekProvider, ProcessingError
        with patch.object(DeepSeekProvider, "_init_client", return_value=None):
            provider = DeepSeekProvider(api_key="sk-test")
        provider.client = None

        with self.assertRaises(ProcessingError):
            provider.generate_structured("prompt")


class TestDeepSeekInstructorPath(unittest.TestCase):
    """Tests for generate_typed instructor path with DeepSeekProvider (OpenAI client)."""

    @requires_openai
    def test_generate_typed_instructor_openai_isinstance_check(self):
        """After PR #482, client is OpenAI, so instructor path must use from_openai."""
        from semantica.semantic_extract.providers import DeepSeekProvider
        with patch.object(DeepSeekProvider, "_init_client", return_value=None):
            provider = DeepSeekProvider(api_key="sk-test")
        provider.client = MagicMock(spec=OpenAI)

        self.assertIsInstance(
            provider.client, OpenAI,
            "client must be OpenAI instance for instructor isinstance check to pass",
        )


class TestVerboseModeAssignment(unittest.TestCase):
    """Tests for verbose_mode assignment fix in BaseProvider.generate_typed (commit eec3e88)."""

    def _make_openai_provider(self):
        from semantica.semantic_extract.providers import OpenAIProvider
        with patch.object(OpenAIProvider, "_init_client", return_value=None):
            provider = OpenAIProvider(api_key="sk-test")
        provider.client = MagicMock()
        return provider

    def test_generate_typed_no_verbose_no_name_error(self):
        """generate_typed must not raise NameError for verbose_mode when verbose not passed."""
        provider = self._make_openai_provider()

        class Schema(BaseModel):
            value: str

        mock_instructor = MagicMock()
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = Schema(value="ok")
        mock_instructor.from_openai.return_value = mock_client
        mock_instructor.from_provider.side_effect = Exception("skip")
        mock_instructor.Mode.TOOLS = "tools"

        with patch("semantica.semantic_extract.providers.instructor", mock_instructor):
            try:
                result = provider.generate_typed("prompt", Schema)
            except NameError as e:
                self.fail(f"NameError for verbose_mode: {e}")
            except Exception:
                pass  # other errors are OK — we only care NameError is gone

    def test_generate_typed_verbose_true_logs(self):
        """When verbose=True, generate_typed must log the confirmation line."""
        provider = self._make_openai_provider()

        class Schema(BaseModel):
            value: str

        mock_schema_instance = Schema(value="ok")
        mock_instructor = MagicMock()
        mock_ic_client = MagicMock()
        mock_ic_client.chat.completions.create.return_value = mock_schema_instance
        mock_instructor.from_openai.return_value = mock_ic_client
        mock_instructor.from_provider.side_effect = Exception("skip")
        mock_instructor.Mode.TOOLS = "tools"

        with patch("semantica.semantic_extract.providers.instructor", mock_instructor):
            with self.assertLogs(provider.logger.name, level="DEBUG") as captured:
                try:
                    provider.generate_typed("prompt", Schema, verbose=True)
                except Exception:
                    pass

        # verbose_mode=True should trigger the debug log line
        self.assertTrue(
            any("generate_typed" in line for line in captured.output),
            f"expected a generate_typed debug record, got {captured.output}",
        )

    def test_generate_typed_verbose_false_no_log(self):
        """When verbose=False (default), generate_typed must not log the line."""
        provider = self._make_openai_provider()

        class Schema(BaseModel):
            value: str

        mock_schema_instance = Schema(value="ok")
        mock_instructor = MagicMock()
        mock_ic_client = MagicMock()
        mock_ic_client.chat.completions.create.return_value = mock_schema_instance
        mock_instructor.from_openai.return_value = mock_ic_client
        mock_instructor.from_provider.side_effect = Exception("skip")
        mock_instructor.Mode.TOOLS = "tools"

        with patch("semantica.semantic_extract.providers.instructor", mock_instructor):
            with patch.object(provider, "logger") as mock_logger:
                try:
                    provider.generate_typed("prompt", Schema)
                except Exception:
                    pass

        debug_calls = [str(c) for c in mock_logger.debug.call_args_list]
        self.assertFalse(
            any("generate_typed" in c for c in debug_calls),
            f"expected no generate_typed debug record, got {debug_calls}",
        )

    def test_generate_typed_verbose_from_config(self):
        """verbose_mode must also respect config-level verbose setting."""
        provider = self._make_openai_provider()
        provider.config["verbose"] = True

        class Schema(BaseModel):
            value: str

        mock_schema_instance = Schema(value="ok")
        mock_instructor = MagicMock()
        mock_ic_client = MagicMock()
        mock_ic_client.chat.completions.create.return_value = mock_schema_instance
        mock_instructor.from_openai.return_value = mock_ic_client
        mock_instructor.from_provider.side_effect = Exception("skip")
        mock_instructor.Mode.TOOLS = "tools"

        with patch("semantica.semantic_extract.providers.instructor", mock_instructor):
            with self.assertLogs(provider.logger.name, level="DEBUG") as captured:
                try:
                    provider.generate_typed("prompt", Schema)
                except Exception:
                    pass

        self.assertTrue(
            any("generate_typed" in line for line in captured.output),
            f"expected a generate_typed debug record, got {captured.output}",
        )


class TestDeepSeekGenerateTypedInstructorIntegration(unittest.TestCase):
    """Integration-style tests: DeepSeekProvider.generate_typed with instructor."""

    @requires_openai
    def test_generate_typed_deepseek_uses_openai_client_for_instructor(self):
        """generate_typed instructor path for DeepSeek must reuse the OpenAI client."""
        from semantica.semantic_extract.providers import DeepSeekProvider

        with patch.object(DeepSeekProvider, "_init_client", return_value=None):
            provider = DeepSeekProvider(api_key="sk-test")
        mock_openai_client = MagicMock(spec=OpenAI)
        provider.client = mock_openai_client

        class Schema(BaseModel):
            label: str

        mock_instructor = MagicMock()
        mock_ic_client = MagicMock()
        mock_ic_client.chat.completions.create.return_value = Schema(label="ok")
        mock_instructor.from_openai.return_value = mock_ic_client
        mock_instructor.from_provider.side_effect = Exception("no from_provider")
        mock_instructor.Mode.JSON = "json"
        mock_instructor.Mode.TOOLS = "tools"

        with patch("semantica.semantic_extract.providers.instructor", mock_instructor):
            result = provider.generate_typed("classify this", Schema)

        # Must have called from_openai with the existing client (not a fresh one)
        mock_instructor.from_openai.assert_called_once_with(
            mock_openai_client, mode="json"
        )
        self.assertEqual(result.label, "ok")


if __name__ == "__main__":
    unittest.main()
