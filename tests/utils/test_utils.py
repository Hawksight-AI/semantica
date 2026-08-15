import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path
import json
import semantica.utils.helpers as helpers
import semantica.utils.validators as validators
from semantica.utils.exceptions import ValidationError

class TestHelpers(unittest.TestCase):

    def test_clean_text(self):
        self.assertEqual(helpers.clean_text("  Hello   World  "), "Hello World")
        self.assertEqual(helpers.clean_text("Line 1\nLine 2"), "Line 1 Line 2")

    def test_format_data_json(self):
        data = {"key": "value"}
        formatted = helpers.format_data(data, "json")
        self.assertIn('"key": "value"', formatted)

    def test_format_data_invalid(self):
        with self.assertRaises(ValueError):
            helpers.format_data({}, "unknown")

    def test_ensure_directory(self):
        with patch("pathlib.Path.mkdir") as mock_mkdir:
            helpers.ensure_directory("test_dir")
            mock_mkdir.assert_called_once()

    def test_merge_dicts(self):
        dict1 = {"a": 1, "b": {"c": 2}}
        dict2 = {"b": {"d": 3}, "e": 4}
        merged = helpers.merge_dicts(dict1, dict2, deep=True)
        self.assertEqual(merged, {"a": 1, "b": {"c": 2, "d": 3}, "e": 4})

    def test_flatten_dict(self):
        """Basic nested flattening with multiple sibling keys."""
        data = {"a": {"b": 1, "c": 2}, "d": 3}
        result = helpers.flatten_dict(data)
        self.assertEqual(result, {"a.b": 1, "a.c": 2, "d": 3})

    def test_flatten_dict_deeply_nested(self):
        """Deeply nested structure is fully flattened."""
        self.assertEqual(
            helpers.flatten_dict({"a": {"b": {"c": 1}}}),
            {"a.b.c": 1},
        )

    def test_flatten_dict_custom_separator(self):
        """Custom separator is used in generated keys."""
        self.assertEqual(
            helpers.flatten_dict({"a": {"b": 1}}, sep="__"),
            {"a__b": 1},
        )

    def test_flatten_dict_empty(self):
        """Empty input returns empty output."""
        self.assertEqual(helpers.flatten_dict({}), {})

    def test_flatten_dict_key_collision(self):
        """#1010 regression: a top-level key containing the separator must not
        silently overwrite a value produced from a nested dict when both resolve
        to the same flattened key.  Before the fix, {'a.b': 1, 'a': {'b': 2}}
        silently dropped one value; now it raises ValueError."""
        with self.assertRaises(ValueError) as ctx:
            helpers.flatten_dict({"a.b": 1, "a": {"b": 2}})
        self.assertIn("Key collision", str(ctx.exception))
        self.assertIn("a.b", str(ctx.exception))

    def test_flatten_dict_no_false_positive(self):
        """Similar-looking keys that produce distinct flattened keys must not
        trigger the collision guard."""
        self.assertEqual(
            helpers.flatten_dict({"a.b": 1, "a": {"c": 2}}),
            {"a.b": 1, "a.c": 2},
        )

    def test_safe_import_returns_module_and_flag(self):
        module, available = helpers.safe_import("json")
        self.assertTrue(available)
        self.assertIs(module, json)

class TestValidators(unittest.TestCase):

    def test_validate_data_required_fields(self):
        data = {"name": "Alice"}
        is_valid, error = validators.validate_data(
            data, required_fields=["name", "age"]
        )
        self.assertFalse(is_valid)
        self.assertIn("age", error)

    def test_validate_data_types(self):
        data = {"name": "Alice", "age": "30"}
        is_valid, error = validators.validate_data(
            data, field_types={"name": str, "age": int}
        )
        self.assertFalse(is_valid)
        self.assertIn("age", error)

    def test_validate_entity(self):
        entity = {"id": "e1", "text": "Alice", "type": "Person"}
        is_valid, error = validators.validate_entity(entity)
        self.assertTrue(is_valid)

    def test_validate_entity_invalid(self):
        entity = {"text": "Alice"} # Missing id and type
        is_valid, error = validators.validate_entity(entity)
        self.assertFalse(is_valid)

    def test_validate_url(self):
        self.assertTrue(validators.validate_url("https://example.com")[0])
        self.assertFalse(validators.validate_url("invalid-url")[0])

    def test_validate_email(self):
        self.assertTrue(validators.validate_email("test@example.com")[0])
        self.assertFalse(validators.validate_email("invalid-email")[0])

if __name__ == "__main__":
    unittest.main()
