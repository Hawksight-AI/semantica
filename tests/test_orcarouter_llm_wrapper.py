"""Tests for the semantica.llms.OrcaRouter wrapper class."""

import sys
import os
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from semantica.llms import OrcaRouter


class TestOrcaRouterWrapper(unittest.TestCase):
    """Tests for the OrcaRouter clean-interface wrapper."""

    def test_import_exported(self):
        """OrcaRouter must be importable from semantica.llms."""
        self.assertTrue(callable(OrcaRouter))

    def test_init_wraps_provider(self):
        """The wrapper must delegate to OrcaRouterProvider."""
        from semantica.semantic_extract.providers import OrcaRouterProvider

        with patch.object(OrcaRouterProvider, "_init_client", return_value=None):
            llm = OrcaRouter(model="openai/gpt-4o", api_key="sk-orca-test")
        # Compare by class name: provider modules can be re-imported during the
        # test session (importlib.reload pattern used by the DeepSeek tests), so
        # object identity across module reloads is not guaranteed.
        self.assertEqual(llm.provider.__class__.__name__, "OrcaRouterProvider")
        self.assertEqual(llm.provider.base_url, "https://api.orcarouter.ai/v1")
        self.assertEqual(llm.model, "openai/gpt-4o")
        self.assertEqual(llm.api_key, "sk-orca-test")

    def test_is_available_delegates(self):
        from semantica.semantic_extract.providers import OrcaRouterProvider

        with patch.object(OrcaRouterProvider, "_init_client", return_value=None):
            llm = OrcaRouter(api_key="sk-orca-test")
        llm.provider.client = MagicMock()
        self.assertTrue(llm.is_available())

    def test_generate_delegates(self):
        from semantica.semantic_extract.providers import OrcaRouterProvider

        with patch.object(OrcaRouterProvider, "_init_client", return_value=None):
            llm = OrcaRouter(api_key="sk-orca-test")
        llm.provider.client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.choices[0].message.content = "pong"
        llm.provider.client.chat.completions.create.return_value = mock_resp
        self.assertEqual(llm.generate("ping"), "pong")

    def test_generate_raises_when_not_available(self):
        from semantica.semantic_extract.providers import (
            OrcaRouterProvider,
            ProcessingError,
        )

        with patch.object(OrcaRouterProvider, "_init_client", return_value=None):
            llm = OrcaRouter(api_key="sk-orca-test")
        llm.provider.client = None
        with self.assertRaises(ProcessingError):
            llm.generate("ping")

    def test_generate_structured_delegates(self):
        from semantica.semantic_extract.providers import OrcaRouterProvider

        with patch.object(OrcaRouterProvider, "_init_client", return_value=None):
            llm = OrcaRouter(api_key="sk-orca-test")
        llm.provider.client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.choices[0].message.content = '{"ok": true}'
        llm.provider.client.chat.completions.create.return_value = mock_resp
        self.assertEqual(llm.generate_structured("ping"), {"ok": True})


if __name__ == "__main__":
    unittest.main()
