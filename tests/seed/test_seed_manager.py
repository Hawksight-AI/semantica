import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from semantica.seed.seed_manager import SeedData, SeedDataManager, SeedDataSource
from semantica.utils.exceptions import ProcessingError


class TestSeedDataManager(unittest.TestCase):

    def setUp(self):
        self.manager = SeedDataManager()

    def test_initialization(self):
        self.assertIsInstance(self.manager, SeedDataManager)
        self.assertEqual(self.manager.sources, {})
        self.assertIsInstance(self.manager.seed_data, SeedData)
        self.assertEqual(self.manager.versions, {})

    def test_register_source(self):
        name = "test_source"
        format = "csv"
        location = "test.csv"
        
        result = self.manager.register_source(name, format, location, entity_type="Person")
        
        self.assertTrue(result)
        self.assertIn(name, self.manager.sources)
        source = self.manager.sources[name]
        self.assertIsInstance(source, SeedDataSource)
        self.assertEqual(source.name, name)
        self.assertEqual(source.format, format)
        self.assertEqual(source.location, location)
        self.assertEqual(source.entity_type, "Person")
        self.assertIn(name, self.manager.versions)

    def test_load_from_csv(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            csv_file = Path(tmp_dir) / "test.csv"
            csv_file.write_text("name,age\nAlice,30\nBob,25", encoding="utf-8")

            records = self.manager.load_from_csv(
                csv_file, entity_type="Person", source_name="test_source"
            )

        self.assertEqual(len(records), 2)
        self.assertEqual(records[0]["name"], "Alice")
        self.assertEqual(records[0]["age"], "30")
        self.assertEqual(records[0]["entity_type"], "Person")
        self.assertEqual(records[0]["source"], "test_source")

    @patch("pathlib.Path.exists")
    def test_load_from_csv_file_not_found(self, mock_exists):
        mock_exists.return_value = False
        
        with self.assertRaises(ProcessingError):
            self.manager.load_from_csv("nonexistent.csv")

    @patch("semantica.seed.seed_manager.read_json_file")
    @patch("pathlib.Path.exists")
    def test_load_from_json(self, mock_exists, mock_read_json):
        mock_exists.return_value = True
        mock_read_json.return_value = [{"name": "Alice", "age": 30}, {"name": "Bob", "age": 25}]
        
        records = self.manager.load_from_json("test.json", entity_type="Person", source_name="test_source")
        
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0]["name"], "Alice")
        self.assertEqual(records[0]["age"], 30)
        self.assertEqual(records[0]["entity_type"], "Person")
        self.assertEqual(records[0]["source"], "test_source")

    @patch("semantica.seed.seed_manager.read_json_file")
    @patch("pathlib.Path.exists")
    def test_load_from_json_dict(self, mock_exists, mock_read_json):
        mock_exists.return_value = True
        mock_read_json.return_value = {"entities": [{"name": "Alice", "age": 30}]}
        
        records = self.manager.load_from_json("test.json", entity_type="Person")
        
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["name"], "Alice")
        self.assertEqual(records[0]["entity_type"], "Person")

if __name__ == "__main__":
    unittest.main()
