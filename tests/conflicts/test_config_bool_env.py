'''Regression tests for issue #1035.

Config.get() must honor boolean environment overrides. Previously the type
dispatch checked isinstance(default, int) before isinstance(default, bool);
since bool subclasses int the bool branch was unreachable, so a boolean
default silently ignored the environment variable (or returned an int when the
value happened to parse).
'''

import os
import unittest
from unittest.mock import patch

from semantica.conflicts.config import ConflictsConfig
from semantica.deduplication.config import DeduplicationConfig
from semantica.embeddings.config import EmbeddingsConfig
from semantica.export.config import ExportConfig
from semantica.ingest.config import IngestConfig
from semantica.kg.config import KGConfig
from semantica.normalize.config import NormalizeConfig
from semantica.ontology.config import OntologyConfig
from semantica.parse.config import ParseConfig
from semantica.split.config import SplitConfig


# The three modules whose get() reaches the type dispatch (no generic
# PREFIX_* scanner in _load_env_vars pre-populates _configs).
_DISPATCH_MODULES = [
    ("conflicts", "CONFLICT", ConflictsConfig),
    ("deduplication", "DEDUP", DeduplicationConfig),
    ("split", "SPLIT", SplitConfig),
]


class TestConfigBoolEnvOverride(unittest.TestCase):
    """Boolean env overrides must reach Config.get() on the dispatch path."""

    def test_conflicts_bool_true(self):
        with patch.dict(os.environ, {"CONFLICT_ZZTESTFLAG": "true"}):
            self.assertIs(ConflictsConfig().get("zztestflag", False), True)

    def test_conflicts_bool_false(self):
        with patch.dict(os.environ, {"CONFLICT_ZZTESTFLAG": "false"}):
            self.assertIs(ConflictsConfig().get("zztestflag", True), False)

    def test_conflicts_int_still_parsed(self):
        with patch.dict(os.environ, {"CONFLICT_ZZTESTFLAG": "42"}):
            self.assertEqual(ConflictsConfig().get("zztestflag", 0), 42)

    def test_conflicts_float_still_parsed(self):
        with patch.dict(os.environ, {"CONFLICT_ZZTESTFLAG": "1.5"}):
            self.assertEqual(ConflictsConfig().get("zztestflag", 0.0), 1.5)

    def test_conflicts_str_still_returned(self):
        with patch.dict(os.environ, {"CONFLICT_ZZTESTFLAG": "some-value"}):
            self.assertEqual(ConflictsConfig().get("zztestflag", "x"), "some-value")

    def test_truthy_spellings(self):
        for value in ["true", "1", "yes", "on", "TRUE", "True", "YES", "ON", " true "]:
            with patch.dict(os.environ, {"CONFLICT_ZZTESTFLAG": value}):
                self.assertIs(
                    ConflictsConfig().get("zztestflag", False),
                    True,
                    msg="value {0!r} should parse as True".format(value),
                )

    def test_falsy_spellings(self):
        for value in ["false", "0", "no", "off", "FALSE", "False", "NO", "OFF", " false "]:
            with patch.dict(os.environ, {"CONFLICT_ZZTESTFLAG": value}):
                self.assertIs(
                    ConflictsConfig().get("zztestflag", True),
                    False,
                    msg="value {0!r} should parse as False".format(value),
                )

    def test_programmatic_config_takes_precedence(self):
        cfg = ConflictsConfig()
        cfg.set("zztestflag", "nope")
        with patch.dict(os.environ, {"CONFLICT_ZZTESTFLAG": "true"}):
            self.assertEqual(cfg.get("zztestflag", False), "nope")

    def test_non_bool_value_falls_back_to_default(self):
        # "not-a-number" is not in the truthy set -> False for a bool default;
        # the int branch would have raised and swallowed the env var entirely.
        with patch.dict(os.environ, {"CONFLICT_ZZTESTFLAG": "not-a-number"}):
            self.assertIs(ConflictsConfig().get("zztestflag", True), False)

    def test_bool_dispatch_across_three_modules(self):
        for name, prefix, cls in _DISPATCH_MODULES:
            env_key = prefix + "_ZZTESTFLAG"
            with self.subTest(module=name, env_key=env_key):
                with patch.dict(os.environ, {env_key: "true"}):
                    self.assertIs(cls().get("zztestflag", False), True)
                with patch.dict(os.environ, {env_key: "false"}):
                    self.assertIs(cls().get("zztestflag", True), False)
                with patch.dict(os.environ, {env_key: "1"}):
                    self.assertIs(cls().get("zztestflag", False), True)
                with patch.dict(os.environ, {env_key: "0"}):
                    self.assertIs(cls().get("zztestflag", True), False)


# Every module config also maps known boolean env vars in _load_env_vars;
# those must parse as real bools too (not ints or strings).
_MAPPED_BOOL_ENV = [
    ("conflicts", "CONFLICT_AUTO_RESOLVE", ConflictsConfig),
    ("deduplication", "DEDUP_USE_CLUSTERING", DeduplicationConfig),
    ("embeddings", "EMBEDDING_NORMALIZE", EmbeddingsConfig),
    ("export", "EXPORT_VALIDATE", ExportConfig),
    ("ingest", "INGEST_RECURSIVE", IngestConfig),
    ("kg", "KG_MERGE_ENTITIES", KGConfig),
    ("ontology", "ONTOLOGY_CHECK_CONSISTENCY", OntologyConfig),
    ("parse", "PARSE_EXTRACT_TABLES", ParseConfig),
]

# Modules that only reach bool env parsing via the generic PREFIX_* scanner
# in _load_env_vars (no bool entry in env_mappings).
_SCANNER_BOOL_ENV = [
    ("split", "SPLIT_ZZTESTFLAG", SplitConfig),
    ("normalize", "NORMALIZE_ZZTESTFLAG", NormalizeConfig),
]


class TestMappedBoolEnvVars(unittest.TestCase):
    def test_mapped_bool_true(self):
        for module, env_key, cls in _MAPPED_BOOL_ENV:
            with self.subTest(module=module, env_key=env_key):
                with patch.dict(os.environ, {env_key: "true"}):
                    cfg = cls()
                    key = env_key.split("_", 1)[1].lower()
                    self.assertIs(cfg.get(key, False), True)

    def test_mapped_bool_false(self):
        for module, env_key, cls in _MAPPED_BOOL_ENV:
            with self.subTest(module=module, env_key=env_key):
                with patch.dict(os.environ, {env_key: "false"}):
                    cfg = cls()
                    key = env_key.split("_", 1)[1].lower()
                    self.assertIs(cfg.get(key, True), False)

    def test_mapped_bool_with_whitespace(self):
        # Qodo follow-up: _load_env_vars() must strip like get() does, so a
        # padded value (" true ") is not silently parsed as False.
        for module, env_key, cls in _MAPPED_BOOL_ENV:
            with self.subTest(module=module, env_key=env_key):
                with patch.dict(os.environ, {env_key: " true "}):
                    cfg = cls()
                    key = env_key.split("_", 1)[1].lower()
                    self.assertIs(cfg.get(key, False), True)

    def test_scanner_bool_true(self):
        for module, env_key, cls in _SCANNER_BOOL_ENV:
            with self.subTest(module=module, env_key=env_key):
                with patch.dict(os.environ, {env_key: "true"}):
                    cfg = cls()
                    key = env_key.split("_", 1)[1].lower()
                    self.assertIs(cfg.get(key, False), True)

    def test_scanner_bool_with_whitespace(self):
        for module, env_key, cls in _SCANNER_BOOL_ENV:
            with self.subTest(module=module, env_key=env_key):
                with patch.dict(os.environ, {env_key: " true "}):
                    cfg = cls()
                    key = env_key.split("_", 1)[1].lower()
                    self.assertIs(cfg.get(key, False), True)


if __name__ == "__main__":
    unittest.main()
