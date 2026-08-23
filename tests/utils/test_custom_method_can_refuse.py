"""
Regression tests for #1108.

Every module supporting custom methods wrapped the registered callable in a
bare `except Exception`, logged a warning, and continued into the built-in
implementation. That makes a registered method advisory: it can add behaviour,
but it cannot decline.

For a gate, a validator or a policy check, declining is the entire purpose.
The demonstration below is the one from the issue: a verifier rejects invalid
RDF and deletes the file, and the swallowed exception lets the default write it
straight back.
"""

import json
from pathlib import Path

import pytest

from semantica.export import methods as export_methods
from semantica.export.registry import method_registry
from semantica.utils.custom_methods import (
    CUSTOM_METHOD_FELL_BACK,
    call_custom_method,
)


class Refused(Exception):
    """Raised by a gate that declines to produce output."""


@pytest.fixture(autouse=True)
def _clean_registry():
    method_registry.clear("rdf")
    yield
    method_registry.clear("rdf")


KG = {"entities": [{"id": "e1", "text": "Acme", "type": "ORG"}], "relationships": []}


def test_a_registered_gate_can_refuse(tmp_path):
    """The exception must reach the caller instead of being logged and dropped."""
    def gate(data, file_path, **kwargs):
        raise Refused("this graph does not pass validation")

    method_registry.register("rdf", "gate", gate)

    with pytest.raises(Refused):
        export_methods.export_rdf(KG, str(tmp_path / "out.ttl"), method="gate")


def test_a_refusal_leaves_no_output_behind(tmp_path):
    """The issue's demonstration: the default used to write the file back."""
    target = tmp_path / "out.ttl"

    def gate(data, file_path, **kwargs):
        Path(file_path).unlink(missing_ok=True)
        raise Refused("rejected by the verifier")

    method_registry.register("rdf", "gate", gate)

    with pytest.raises(Refused):
        export_methods.export_rdf(KG, str(target), method="gate")

    assert not target.exists(), (
        "the default implementation wrote the file the gate refused to produce"
    )


def test_a_custom_method_that_succeeds_is_unaffected(tmp_path):
    target = tmp_path / "out.ttl"

    def writer(data, file_path, **kwargs):
        Path(file_path).write_text("# written by the custom method\n")
        return {"written_by": "custom"}

    method_registry.register("rdf", "writer", writer)
    result = export_methods.export_rdf(KG, str(target), method="writer")

    assert result == {"written_by": "custom"}
    assert target.read_text().startswith("# written by the custom method")


def test_the_old_behaviour_is_available_as_an_explicit_opt_in(tmp_path):
    target = tmp_path / "out.ttl"

    def gate(data, file_path, **kwargs):
        raise Refused("rejected")

    method_registry.register("rdf", "gate", gate)
    export_methods.export_rdf(
        KG, str(target), method="gate", fallback_on_custom_error=True
    )

    assert target.exists(), "opting in should still fall through to the default"


def test_the_reserved_keyword_is_never_forwarded():
    """`fallback_on_custom_error` is consumed by the policy, not by the method."""
    seen = {}

    def recorder(**kwargs):
        seen.update(kwargs)
        return "ok"

    result = call_custom_method(
        _NullLogger(), "recorder", recorder, alpha=1, fallback_on_custom_error=True
    )

    assert result == "ok"
    assert seen == {"alpha": 1}


class _NullLogger:
    def warning(self, *args, **kwargs):
        self.last = args


def test_the_sentinel_is_returned_only_on_the_opt_in_path():
    def boom():
        raise Refused("no")

    logger = _NullLogger()
    assert call_custom_method(
        logger, "boom", boom, fallback_on_custom_error=True
    ) is CUSTOM_METHOD_FELL_BACK

    with pytest.raises(Refused):
        call_custom_method(logger, "boom", boom)


def test_a_falsy_return_value_is_not_mistaken_for_a_failure():
    """`is not CUSTOM_METHOD_FELL_BACK` matters: None and 0 are real results."""
    for value in (None, 0, "", False, []):
        assert call_custom_method(_NullLogger(), "m", lambda: value) is value


@pytest.mark.parametrize(
    "module_name",
    ["export", "ingest", "parse", "normalize", "embeddings", "kg"],
)
def test_no_module_still_swallows_custom_method_failures(module_name):
    """The swallow was repeated across six modules, not just the one filed."""
    import semantica

    # Read the file rather than import it: some of these modules pull in
    # optional third-party dependencies that need not be installed to check
    # that the swallow is gone.
    source = (
        Path(semantica.__file__).parent / module_name / "methods.py"
    ).read_text(encoding="utf-8")

    assert "falling back to default" not in source, (
        f"semantica/{module_name}/methods.py still swallows custom method failures"
    )


# ── Review findings on the first revision of this fix ────────────────────────

def test_the_reserved_flag_never_reaches_the_default_implementation(monkeypatch, tmp_path):
    """
    `**kwargs` unpacking builds a fresh dict inside the helper, so popping there
    left the caller's own kwargs untouched and the flag was forwarded on to the
    default path. The helper documents the flag as never forwarded, so that
    promise was false for exactly the case the flag exists for.
    """
    seen = {}

    class Spy:
        def __init__(self, **config):
            seen.update(config)

        def export(self, *args, **kwargs):
            (tmp_path / "written").write_text("default ran")

    monkeypatch.setattr(export_methods, "RDFExporter", Spy)

    def gate(data, file_path, **kwargs):
        raise Refused("rejected")

    method_registry.register("rdf", "gate", gate)
    export_methods.export_rdf(
        KG, str(tmp_path / "out.ttl"), method="gate", fallback_on_custom_error=True
    )

    assert (tmp_path / "written").exists(), "the default path did not run"
    assert "fallback_on_custom_error" not in seen, (
        f"the reserved flag was forwarded to the default implementation: {seen}"
    )


def test_the_reserved_flag_never_reaches_a_successful_custom_method(tmp_path):
    seen = {}

    def writer(data, file_path, **kwargs):
        seen.update(kwargs)
        return "ok"

    method_registry.register("rdf", "writer", writer)
    result = export_methods.export_rdf(
        KG, str(tmp_path / "out.ttl"), method="writer", fallback_on_custom_error=True
    )

    assert result == "ok"
    assert "fallback_on_custom_error" not in seen, seen


@pytest.mark.parametrize(
    "module_name", ["export", "ingest", "parse", "normalize", "embeddings", "kg"],
)
def test_every_site_consumes_the_flag_before_forwarding(module_name):
    """A site that forgets the pop reintroduces the leak silently."""
    import semantica

    source = (
        Path(semantica.__file__).parent / module_name / "methods.py"
    ).read_text(encoding="utf-8")

    calls = source.count("result = call_custom_method(")
    pops = source.count('.pop("fallback_on_custom_error", False)')
    assert calls == pops, (
        f"semantica/{module_name}/methods.py has {calls} call site(s) but "
        f"{pops} consume the reserved flag"
    )
