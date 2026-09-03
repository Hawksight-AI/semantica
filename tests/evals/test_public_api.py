"""Tests for the evals public package API."""
from semantica import evals
from semantica.evals import evaluate, get_evaluator, list_evaluators


class TestPublicAPI:
    def test_imports(self):
        assert callable(evaluate)
        assert callable(list_evaluators)
        assert callable(get_evaluator)

    def test_version_present(self):
        assert hasattr(evals, "__version__")

    def test_module_proxy_via_root(self):
        # semantica.evals must resolve through the lazy proxy
        assert hasattr(evals, "evaluate")

    def test_all_populated(self):
        assert len(evals.__all__) >= 2
        assert "evaluate" in evals.__all__
        assert "list_evaluators" in evals.__all__
        assert "get_evaluator" in evals.__all__

    def test_register_discovery(self):
        names = evals.list_evaluators()
        for expected in (
            "exact_match", "regex_match", "numeric_range", "temporal_range",
            "length_range", "keyword_check", "levenshtein", "rouge",
            "llm_as_judge", "decision_scores",
        ):
            assert expected in names
