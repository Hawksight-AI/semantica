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
        data = {"a": {"b": 1, "c": 2}}
        result = helpers.flatten_dict(data)
        self.assertEqual(result, {"a.b": 1, "a.c": 2})

    def test_flatten_dict_key_collision(self):
        data = {
            "a.b": 1,
            "a": {
                "b": 2
            }
        }

        with self.assertRaises(ValueError):
            helpers.flatten_dict(data)

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
