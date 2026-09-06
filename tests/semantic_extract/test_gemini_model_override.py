"""Regression tests for the per-call ``model=`` override on ``GeminiProvider``.

``GeminiProvider.generate(model=...)`` and ``generate_structured(model=...)`` must
select the model the same way as each other, on both supported Gemini SDK paths:

* the new ``google.genai`` client (``_use_new_genai = True``), and
* the legacy ``google.generativeai`` package (``_use_new_genai = False``), where a
  per-call model has to be resolved through ``_legacy_client_for()`` because the
  legacy ``GenerativeModel`` binds its model name at construction time.
"""

import sys
from unittest.mock import MagicMock, patch

import pytest

from semantica.semantic_extract.providers import GeminiProvider

CONSTRUCTION_MODEL = "gemini-pro"
OVERRIDE_MODEL = "gemini-1.5-flash"
JSON_TEXT = '{"answer": 42}'


def _make_provider():
    """A GeminiProvider with the real SDK bootstrap skipped."""
    with patch.object(GeminiProvider, "_init_client", return_value=None):
        return GeminiProvider(api_key="fake-key", model=CONSTRUCTION_MODEL)


class TestNewGenaiModelOverride:
    """New ``google.genai`` client path (``_use_new_genai = True``)."""

    @staticmethod
    def _provider():
        provider = _make_provider()
        provider._use_new_genai = True
        client = MagicMock()
        response = MagicMock()
        response.text = JSON_TEXT
        client.models.generate_content.return_value = response
        provider.client = client
        return provider, client

    def test_generate_honors_per_call_model(self):
        provider, client = self._provider()

        provider.generate("hello", model=OVERRIDE_MODEL)

        assert (
            client.models.generate_content.call_args.kwargs["model"] == OVERRIDE_MODEL
        )

    def test_generate_structured_honors_per_call_model(self):
        provider, client = self._provider()

        provider.generate_structured("hello", model=OVERRIDE_MODEL)

        assert (
            client.models.generate_content.call_args.kwargs["model"] == OVERRIDE_MODEL
        )

    def test_generate_falls_back_to_construction_model(self):
        provider, client = self._provider()

        provider.generate("hello")

        assert (
            client.models.generate_content.call_args.kwargs["model"]
            == CONSTRUCTION_MODEL
        )

    def test_generate_structured_falls_back_to_construction_model(self):
        provider, client = self._provider()

        provider.generate_structured("hello")

        assert (
            client.models.generate_content.call_args.kwargs["model"]
            == CONSTRUCTION_MODEL
        )

    def test_both_methods_select_model_consistently(self):
        provider, client = self._provider()

        provider.generate("hello", model=OVERRIDE_MODEL)
        generate_model = client.models.generate_content.call_args.kwargs["model"]

        client.models.generate_content.reset_mock()
        provider.generate_structured("hello", model=OVERRIDE_MODEL)
        structured_model = client.models.generate_content.call_args.kwargs["model"]

        assert generate_model == structured_model == OVERRIDE_MODEL


class TestLegacyModelOverride:
    """Legacy ``google.generativeai`` path (``_use_new_genai = False``)."""

    @pytest.fixture
    def fake_legacy_genai(self, monkeypatch):
        """Install a stand-in ``google.generativeai`` module.

        ``GenerativeModel(name)`` returns a distinct mock per model name (cached,
        mirroring ``_legacy_client_for``) so tests can assert which model name the
        per-call override resolved to.
        """
        module = MagicMock()
        module.created_models = {}

        def make_model(name):
            model = module.created_models.get(name)
            if model is None:
                model = MagicMock(name=f"GenerativeModel({name})")
                response = MagicMock()
                response.text = JSON_TEXT
                model.generate_content.return_value = response
                module.created_models[name] = model
            return model

        module.GenerativeModel.side_effect = make_model
        monkeypatch.setitem(sys.modules, "google.generativeai", module)
        return module

    @staticmethod
    def _provider():
        provider = _make_provider()
        provider._use_new_genai = False
        construction_client = MagicMock(name="construction client")
        response = MagicMock()
        response.text = JSON_TEXT
        construction_client.generate_content.return_value = response
        provider.client = construction_client
        return provider, construction_client

    def test_generate_builds_client_for_per_call_model(self, fake_legacy_genai):
        provider, construction_client = self._provider()

        provider.generate("hello", model=OVERRIDE_MODEL)

        fake_legacy_genai.GenerativeModel.assert_called_once_with(OVERRIDE_MODEL)
        construction_client.generate_content.assert_not_called()

    def test_generate_structured_builds_client_for_per_call_model(
        self, fake_legacy_genai
    ):
        provider, construction_client = self._provider()

        provider.generate_structured("hello", model=OVERRIDE_MODEL)

        fake_legacy_genai.GenerativeModel.assert_called_once_with(OVERRIDE_MODEL)
        construction_client.generate_content.assert_not_called()

    def test_without_override_uses_construction_client(self, fake_legacy_genai):
        provider, construction_client = self._provider()

        provider.generate("hello")
        provider.generate_structured("hello")

        fake_legacy_genai.GenerativeModel.assert_not_called()
        assert construction_client.generate_content.call_count == 2

    def test_both_methods_select_model_consistently(self, fake_legacy_genai):
        provider, construction_client = self._provider()

        provider.generate("hello", model=OVERRIDE_MODEL)
        provider.generate_structured("hello", model=OVERRIDE_MODEL)

        assert set(fake_legacy_genai.created_models) == {OVERRIDE_MODEL}
        assert (
            fake_legacy_genai.created_models[OVERRIDE_MODEL].generate_content.call_count
            == 2
        )
        construction_client.generate_content.assert_not_called()

    def test_generate_structured_still_forwards_generation_config(
        self, fake_legacy_genai
    ):
        """generate_structured() must forward generation params on the legacy path,
        the same as generate() does."""
        provider, _ = self._provider()

        provider.generate_structured("hello", model=OVERRIDE_MODEL, temperature=0.2)

        override_client = fake_legacy_genai.created_models[OVERRIDE_MODEL]
        gen_config = override_client.generate_content.call_args.kwargs[
            "generation_config"
        ]
        assert gen_config["temperature"] == 0.2
