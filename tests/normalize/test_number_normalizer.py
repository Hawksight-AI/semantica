import unittest
from semantica.normalize.number_normalizer import (
    NumberNormalizer,
    UnitConverter,
    CurrencyNormalizer,
    ScientificNotationHandler
)

class TestNumberNormalizer(unittest.TestCase):
    def setUp(self):
        self.normalizer = NumberNormalizer()

    def test_normalize_number_string(self):
        self.assertEqual(self.normalizer.normalize_number("1,234.56"), 1234.56)

    def test_normalize_quantity(self):
        result = self.normalizer.normalize_quantity("5 kg")
        self.assertEqual(result["value"], 5.0)
        self.assertEqual(result["unit"], "kilogram")

        result = self.normalizer.normalize_quantity("100 meters")
        self.assertEqual(result["value"], 100.0)
        self.assertEqual(result["unit"], "meter")

class TestUnitConverter(unittest.TestCase):
    def setUp(self):
        self.converter = UnitConverter()

    def test_convert(self):
        # 1 km = 1000 m
        self.assertEqual(self.converter.convert_units(1, "km", "m"), 1000.0)
        # 1 kg = 1000 g
        self.assertEqual(self.converter.convert_units(1, "kg", "g"), 1000.0)

    def test_normalize_unit(self):
        self.assertEqual(self.converter.normalize_unit("km"), "kilometer")
        self.assertEqual(self.converter.normalize_unit("kgs"), "kilogram")

class TestCurrencyNormalizer(unittest.TestCase):
    def setUp(self):
        self.normalizer = CurrencyNormalizer()

    def test_parse_currency(self):
        result = self.normalizer.normalize_currency("$1,234.56")
        self.assertEqual(result["amount"], 1234.56)
        self.assertEqual(result["currency"], "USD")

        result = self.normalizer.normalize_currency("100 EUR")
        self.assertEqual(result["amount"], 100.0)
        self.assertEqual(result["currency"], "EUR")

    def test_symbol_currencies_are_validated_as_supported_codes(self):
        for symbol, expected_code in self.normalizer.currency_symbols.items():
            result = self.normalizer.normalize_currency(f"{symbol}100")
            self.assertEqual(result["currency"], expected_code)
            self.assertTrue(self.normalizer.validate_currency_code(result["currency"]))

    def test_currency_codes_match_boundaries_without_matching_words(self):
        for value in ("RUB100", "100 RUB", "rub 100"):
            result = self.normalizer.normalize_currency(value)
            self.assertEqual(result["amount"], 100.0)
            self.assertEqual(result["currency"], "RUB")

        for value in ("ruby 100", "wilson 100"):
            result = self.normalizer.normalize_currency(value)
            self.assertEqual(result["amount"], 100.0)
            self.assertEqual(result["currency"], "USD")


class TestScientificNotationHandler(unittest.TestCase):
    def setUp(self):
        self.handler = ScientificNotationHandler()

    def test_parse_scientific(self):
        self.assertEqual(self.handler.parse_scientific_notation("1.23e4"), 12300.0)
        self.assertEqual(self.handler.parse_scientific_notation("1.23E-2"), 0.0123)

if __name__ == "__main__":
    unittest.main()
