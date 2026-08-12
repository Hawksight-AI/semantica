"""
Number and Quantity Normalization Module

This module provides comprehensive number and quantity normalization capabilities
for the Semantica framework, enabling standardization of numerical data across
various formats and units.

Key Features:
    - Number format standardization (integers, floats, percentages)
    - Unit conversion and normalization (length, weight, volume)
    - Currency handling (symbols, codes, conversion)
    - Percentage processing
    - Scientific notation handling
    - Quantity parsing and normalization

Main Classes:
    - NumberNormalizer: Main number normalization coordinator
    - UnitConverter: Unit conversion engine
    - CurrencyNormalizer: Currency processing engine
    - ScientificNotationHandler: Scientific notation processor

Example Usage:
    >>> from semantica.normalize import NumberNormalizer
    >>> normalizer = NumberNormalizer()
    >>> number = normalizer.normalize_number("1,234.56")
    >>> quantity = normalizer.normalize_quantity("5 kg")
    >>> currency = normalizer.process_currency("$100")

Author: Semantica Contributors
License: MIT
"""

import re
from typing import Any, Dict, List, Optional, Union

from ..utils.exceptions import ProcessingError, ValidationError
from ..utils.logging import get_logger
from ..utils.progress_tracker import get_progress_tracker


class NumberNormalizer:
    """
    Number and quantity normalization coordinator.

    This class provides comprehensive number and quantity normalization
    capabilities, coordinating unit conversion, currency processing, and
    scientific notation handling.

    Features:
        - Number format standardization
        - Quantity parsing and normalization
        - Unit conversion
        - Currency processing
        - Percentage handling
        - Scientific notation support

    Example Usage:
        >>> normalizer = NumberNormalizer()
        >>> number = normalizer.normalize_number("1,234.56")
        >>> quantity = normalizer.normalize_quantity("5 kg")
        >>> currency = normalizer.process_currency("$100")
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None, **kwargs):
        """
        Initialize number normalizer.

        Sets up the normalizer with unit converter, currency normalizer, and
        scientific notation handler components.

        Args:
            config: Configuration dictionary (optional)
            **kwargs: Additional configuration options (merged into config)
        """
        self.logger = get_logger("number_normalizer")
        self.config = config or {}
        self.config.update(kwargs)

        self.unit_converter = UnitConverter(**self.config)
        self.currency_normalizer = CurrencyNormalizer(**self.config)
        self.scientific_handler = ScientificNotationHandler(**self.config)

        # Initialize progress tracker
        self.progress_tracker = get_progress_tracker()
        # Ensure progress tracker is enabled
        if not self.progress_tracker.enabled:
            self.progress_tracker.enabled = True

        self.logger.debug("Number normalizer initialized")

    def normalize_number(
        self, number_input: Union[str, int, float], **options
    ) -> Union[int, float]:
        """
        Normalize number to standard format.

        This method normalizes number input (string, int, or float) to a
        standard numeric format, handling percentages and scientific notation.

        Args:
            number_input: Number input - can be:
                - String (e.g., "1,234.56", "50%", "1.5e3")
                - int or float
            **options: Normalization options (unused)

        Returns:
            Union[int, float]: Normalized number (int if no decimal, float otherwise)

        Raises:
            ValidationError: If number input type is unsupported or parsing fails
        """
        if isinstance(number_input, (int, float)):
            return number_input

        if not isinstance(number_input, str):
            raise ValidationError(
                f"Unsupported number input type: {type(number_input)}"
            )

        # Remove formatting characters
        cleaned = number_input.replace(",", "").replace(" ", "").strip()

        # Remove currency symbols
        for symbol in self.currency_normalizer.currency_symbols:
            if symbol in cleaned:
                cleaned = cleaned.replace(symbol, "")

        # Handle percentages
        if "%" in cleaned:
            cleaned = cleaned.replace("%", "")
            value = float(cleaned) / 100
            return value

        # Handle scientific notation
        if "e" in cleaned.lower() or "E" in cleaned:
            parsed = self.scientific_handler.parse_scientific_notation(cleaned)
            return parsed

        # Handle suffixes (K, M, B, T)
        suffix_map = {
            'k': 1_000,
            'm': 1_000_000,
            'b': 1_000_000_000,
            't': 1_000_000_000_000
        }
        
        if cleaned and cleaned[-1].lower() in suffix_map:
            last_char = cleaned[-1].lower()
            try:
                number_part = float(cleaned[:-1])
                return number_part * suffix_map[last_char]
            except ValueError:
                pass  # Fall through to standard parsing

        # Parse as float or int
        try:
            if "." in cleaned:
                return float(cleaned)
            else:
                return int(cleaned)
        except ValueError:
            raise ValidationError(f"Unable to parse number: {number_input}")

    def normalize_quantity(self, quantity_input: str, **options) -> Dict[str, Any]:
        """
        Normalize quantity with units.

        This method parses and normalizes quantity strings containing values
        and units (e.g., "5 kg", "10 meters").

        Args:
            quantity_input: Quantity string (e.g., "5 kg", "10 meters", "3.5 liters")
            **options: Normalization options (unused)

        Returns:
            dict: Normalized quantity dictionary containing:
                - value: Numeric value (float)
                - unit: Normalized unit name (str)
                - original: Original quantity string (str)

        Raises:
            ValidationError: If quantity format is invalid or parsing fails
        """
        # Parse quantity and unit
        pattern = r"([\d.,\s]+)\s*([a-zA-Z]+)"
        match = re.search(pattern, quantity_input)

        if match:
            value_str = match.group(1).replace(",", "").replace(" ", "")
            unit = match.group(2).lower()

            try:
                value = float(value_str)

                # Normalize unit
                normalized_unit = self.unit_converter.normalize_unit(unit)

                return {
                    "value": value,
                    "unit": normalized_unit,
                    "original": quantity_input,
                }
            except ValueError:
                raise ValidationError(f"Unable to parse quantity: {quantity_input}")
        else:
            raise ValidationError(f"Invalid quantity format: {quantity_input}")

    def convert_units(self, value: float, from_unit: str, to_unit: str) -> float:
        """
        Convert value between units.

        This method converts a numeric value from one unit to another,
        supporting length, weight, and volume conversions.

        Args:
            value: Numeric value to convert
            from_unit: Source unit (e.g., "kg", "meter", "liter")
            to_unit: Target unit (e.g., "pound", "mile", "gallon")

        Returns:
            float: Converted value in target unit

        Raises:
            ValidationError: If units are incompatible or conversion fails
        """
        return self.unit_converter.convert_units(value, from_unit, to_unit)

    def process_currency(
        self, currency_input: str, default_currency: str = "USD", **options
    ) -> Dict[str, Any]:
        """
        Process currency values.

        This method parses and normalizes currency strings, extracting
        amount and currency code.

        Args:
            currency_input: Currency string (e.g., "$100", "100 USD", "€50")
            default_currency: Default currency code if not found (default: "USD")
            **options: Additional processing options (unused)

        Returns:
            dict: Normalized currency dictionary containing:
                - amount: Numeric amount (float or None)
                - currency: Currency code (str, e.g., "USD", "EUR")
                - original: Original currency string (str)
        """
        return self.currency_normalizer.normalize_currency(
            currency_input, default_currency=default_currency, **options
        )


class UnitConverter:
    """
    Unit conversion engine.

    This class provides unit conversion capabilities, supporting length,
    weight, and volume conversions with validation.

    Features:
        - Unit conversion (length, weight, volume)
        - Conversion factor management
        - Unit validation
        - Unit normalization
        - Support for multiple unit systems

    Example Usage:
        >>> converter = UnitConverter()
        >>> converted = converter.convert_units(100, "kg", "pound")
        >>> normalized = converter.normalize_unit("km")
    """

    def __init__(self, **config):
        """
        Initialize unit converter.

        Sets up the converter with conversion factors and unit categories.

        Args:
            **config: Configuration options (currently unused)
        """
        self.logger = get_logger("unit_converter")
        self.config = config

        # Unit conversion factors (to base unit)
        self.conversion_factors = {
            # Length
            "meter": 1.0,
            "meters": 1.0,
            "m": 1.0,
            "kilometer": 1000.0,
            "kilometers": 1000.0,
            "km": 1000.0,
            "centimeter": 0.01,
            "centimeters": 0.01,
            "cm": 0.01,
            "millimeter": 0.001,
            "millimeters": 0.001,
            "mm": 0.001,
            "inch": 0.0254,
            "inches": 0.0254,
            "in": 0.0254,
            "foot": 0.3048,
            "feet": 0.3048,
            "ft": 0.3048,
            "yard": 0.9144,
            "yards": 0.9144,
            "yd": 0.9144,
            "mile": 1609.34,
            "miles": 1609.34,
            "mi": 1609.34,
            # Weight
            "kilogram": 1.0,
            "kilograms": 1.0,
            "kg": 1.0,
            "gram": 0.001,
            "grams": 0.001,
            "g": 0.001,
            "pound": 0.453592,
            "pounds": 0.453592,
            "lb": 0.453592,
            "ounce": 0.0283495,
            "ounces": 0.0283495,
            "oz": 0.0283495,
            # Volume
            "liter": 1.0,
            "liters": 1.0,
            "l": 1.0,
            "milliliter": 0.001,
            "milliliters": 0.001,
            "ml": 0.001,
            "gallon": 3.78541,
            "gallons": 3.78541,
            "gal": 3.78541,
        }

        # Unit categories
        self.unit_categories = {
            "length": [
                "meter",
                "kilometer",
                "centimeter",
                "millimeter",
                "inch",
                "foot",
                "yard",
                "mile",
            ],
            "weight": ["kilogram", "gram", "pound", "ounce"],
            "volume": ["liter", "milliliter", "gallon"],
        }

        self.logger.debug("Unit converter initialized")

    def convert_units(self, value: float, from_unit: str, to_unit: str) -> float:
        """
        Convert value between units.

        This method converts a numeric value from one unit to another within
        the same category (length, weight, or volume).

        Args:
            value: Numeric value to convert
            from_unit: Source unit name (e.g., "kg", "meter", "liter")
            to_unit: Target unit name (e.g., "pound", "mile", "gallon")

        Returns:
            float: Converted value in target unit

        Raises:
            ValidationError: If units are incompatible or not in same category
        """
        from_unit = from_unit.lower()
        to_unit = to_unit.lower()

        # Validate units
        if not self.validate_units(from_unit, to_unit):
            raise ValidationError(f"Cannot convert from {from_unit} to {to_unit}")

        # Get conversion factors
        from_factor = self.get_conversion_factor(from_unit, "base")
        to_factor = self.get_conversion_factor(to_unit, "base")

        # Convert to base unit, then to target unit
        base_value = value * from_factor
        converted_value = base_value / to_factor

        return converted_value

    def validate_units(self, from_unit: str, to_unit: str) -> bool:
        """
        Validate unit conversion compatibility.

        This method validates that two units are compatible for conversion,
        checking that they exist and are in the same category.

        Args:
            from_unit: Source unit name
            to_unit: Target unit name

        Returns:
            bool: True if units are compatible (same category), False otherwise
        """
        from_unit = from_unit.lower()
        to_unit = to_unit.lower()

        # Check if both units exist
        if (
            from_unit not in self.conversion_factors
            or to_unit not in self.conversion_factors
        ):
            return False

        # Check if units are in same category
        from_category = None
        to_category = None

        for category, units in self.unit_categories.items():
            if from_unit in units:
                from_category = category
            if to_unit in units:
                to_category = category

        return from_category == to_category

    def get_conversion_factor(self, from_unit: str, to_unit: str) -> float:
        """
        Get conversion factor between units.

        This method calculates the conversion factor to convert from one unit
        to another. If to_unit is "base", returns factor to base unit.

        Args:
            from_unit: Source unit name
            to_unit: Target unit name or "base" for base unit

        Returns:
            float: Conversion factor (multiply source value by this to get target)
        """
        from_unit = from_unit.lower()

        if to_unit == "base":
            return self.conversion_factors.get(from_unit, 1.0)

        to_unit = to_unit.lower()
        from_factor = self.conversion_factors.get(from_unit, 1.0)
        to_factor = self.conversion_factors.get(to_unit, 1.0)

        return from_factor / to_factor

    def normalize_unit(self, unit: str) -> str:
        """
        Normalize unit name to standard form.

        This method normalizes unit abbreviations to full unit names
        (e.g., "km" -> "kilometer", "kg" -> "kilogram").

        Args:
            unit: Unit name or abbreviation (e.g., "km", "kg", "m")

        Returns:
            str: Normalized unit name (full name if abbreviation found,
                 original unit otherwise)
        """
        unit_lower = unit.lower()

        # Map to standard unit
        unit_map = {
            "m": "meter",
            "meter": "meter",
            "meters": "meter",
            "km": "kilometer",
            "kilometer": "kilometer",
            "kilometers": "kilometer",
            "cm": "centimeter",
            "centimeter": "centimeter",
            "centimeters": "centimeter",
            "mm": "millimeter",
            "millimeter": "millimeter",
            "millimeters": "millimeter",
            "kg": "kilogram",
            "kilogram": "kilogram",
            "kilograms": "kilogram",
            "kgs": "kilogram",
            "g": "gram",
            "gram": "gram",
            "grams": "gram",
            "lb": "pound",
            "pound": "pound",
            "pounds": "pound",
            "lbs": "pound",
            "oz": "ounce",
            "ounce": "ounce",
            "ounces": "ounce",
            "l": "liter",
            "liter": "liter",
            "liters": "liter",
            "ml": "milliliter",
            "milliliter": "milliliter",
            "milliliters": "milliliter",
        }

        return unit_map.get(unit_lower, unit_lower)


class CurrencyNormalizer:
    """
    Currency normalization engine.

    This class provides currency processing capabilities, including symbol
    and code recognition, amount extraction, and currency validation.

    Features:
        - Currency symbol and code recognition
        - Amount extraction from currency strings
        - Currency code validation
        - Support for multiple currencies
        - Currency conversion (placeholder for exchange rate integration)

    Example Usage:
        >>> normalizer = CurrencyNormalizer()
        >>> result = normalizer.normalize_currency("$100")
        >>> is_valid = normalizer.validate_currency_code("USD")
    """

    def __init__(self, **config):
        """
        Initialize currency normalizer.

        Sets up the normalizer with currency symbols and codes dictionaries.

        Args:
            **config: Configuration options (currently unused)
        """
        self.logger = get_logger("currency_normalizer")
        self.config = config

        # Currency symbols and codes
        self.currency_symbols = {
            "$": "USD",
            "€": "EUR",
            "£": "GBP",
            "¥": "JPY",
            "₹": "INR",
            "₽": "RUB",
            "₩": "KRW",
            "₪": "ILS",
            "₦": "NGN",
            "₨": "PKR",
        }

        self.currency_codes = [
            "USD",
            "EUR",
            "GBP",
            "JPY",
            "CNY",
            "INR",
            "AUD",
            "CAD",
            "CHF",
            "SEK",
            "NOK",
            "DKK",
            "RUB",
            "KRW",
            "ILS",
            "NGN",
            "PKR",
        ]

        self.logger.debug("Currency normalizer initialized")

    def normalize_currency(
        self, currency_input: str, default_currency: str = "USD", **options
    ) -> Dict[str, Any]:
        """
        Normalize currency value and code.

        This method parses currency strings, extracting amount and currency
        code from symbols or text.

        Args:
            currency_input: Currency string (e.g., "$100", "100 USD", "€50")
            default_currency: Default currency code if not found (default: "USD")
            **options: Additional normalization options (unused)

        Returns:
            dict: Normalized currency dictionary containing:
                - amount: Numeric amount (float or None if not found)
                - currency: Currency code (str, e.g., "USD", "EUR")
                - original: Original currency string (str)
        """
        # Extract currency symbol or code
        currency_code = None
        amount = None

        # Check for currency symbol
        for symbol, code in self.currency_symbols.items():
            if symbol in currency_input:
                currency_code = code
                # Remove symbol and extract amount
                amount_str = currency_input.replace(symbol, "").strip()
                amount_str = amount_str.replace(",", "").replace(" ", "")
                try:
                    amount = float(amount_str)
                except ValueError:
                    pass
                break

        # Check for currency code
        if not currency_code:
            for code in self.currency_codes:
                match = re.search(
                    rf"(?<![A-Z]){re.escape(code)}(?![A-Z])",
                    currency_input.upper(),
                )
                if match:
                    currency_code = code
                    amount_str = (
                        currency_input[: match.start()] + currency_input[match.end() :]
                    ).strip()
                    amount_str = amount_str.replace(",", "").replace(" ", "")
                    try:
                        amount = float(amount_str)
                    except ValueError:
                        pass
                    break

        # Extract amount if not found
        if amount is None:
            amount_str = re.sub(r"[^\d.,]", "", currency_input)
            amount_str = amount_str.replace(",", "").replace(" ", "")
            try:
                amount = float(amount_str)
            except ValueError:
                amount = None

        # Default to specified currency if no currency found
        if not currency_code:
            currency_code = default_currency

        return {"amount": amount, "currency": currency_code, "original": currency_input}

    def convert_currency(
        self, amount: float, from_currency: str, to_currency: str
    ) -> float:
        """
        Convert currency between different currencies.

        This method converts an amount from one currency to another.
        Currently a placeholder; requires exchange rate API integration
        for production use.

        Args:
            amount: Amount to convert
            from_currency: Source currency code (e.g., "USD")
            to_currency: Target currency code (e.g., "EUR")

        Returns:
            float: Converted amount (currently returns original amount)

        Note:
            This is a placeholder implementation. In production, you would
            integrate with an exchange rate API to fetch current rates.
        """
        self.logger.warning("Currency conversion requires exchange rate API")
        return amount

    def validate_currency_code(self, currency_code: str) -> bool:
        """
        Validate currency code.

        This method validates that a currency code is in the supported
        list of currency codes.

        Args:
            currency_code: Currency code to validate (e.g., "USD", "EUR")

        Returns:
            bool: True if currency code is valid, False otherwise
        """
        return currency_code.upper() in self.currency_codes


class ScientificNotationHandler:
    """
    Scientific notation processing engine.

    This class provides scientific notation handling capabilities, including
    parsing, conversion, and precision normalization.

    Features:
        - Scientific notation parsing
        - Format conversion
        - Precision normalization
        - Significant digit handling

    Example Usage:
        >>> handler = ScientificNotationHandler()
        >>> number = handler.parse_scientific_notation("1.5e3")
        >>> notation = handler.convert_to_scientific(1500, precision=2)
    """

    def __init__(self, **config):
        """
        Initialize scientific notation handler.

        Sets up the handler with configuration options.

        Args:
            **config: Configuration options (currently unused)
        """
        self.logger = get_logger("scientific_notation_handler")
        self.config = config

        self.logger.debug("Scientific notation handler initialized")

    def parse_scientific_notation(self, number_string: str) -> float:
        """
        Parse scientific notation number.

        This method parses a scientific notation string (e.g., "1.5e3", "2E-4")
        and returns the numeric value.

        Args:
            number_string: Scientific notation string (e.g., "1.5e3", "2E-4")

        Returns:
            float: Parsed numeric value

        Raises:
            ValidationError: If string is not valid scientific notation
        """
        try:
            return float(number_string)
        except ValueError as e:
            raise ValidationError(
                f"Invalid scientific notation: {number_string}"
            ) from e

    def convert_to_scientific(
        self, number: float, precision: Optional[int] = None
    ) -> str:
        """
        Convert number to scientific notation.

        This method converts a numeric value to scientific notation string
        format (e.g., "1.5e+03").

        Args:
            number: Numeric value to convert
            precision: Number of decimal places (optional, uses default if None)

        Returns:
            str: Scientific notation string (e.g., "1.5e+03", "2.0e-04")
        """
        if precision is not None:
            return f"{number:.{precision}e}"
        else:
            return f"{number:e}"

    def normalize_precision(self, number: float, significant_digits: int) -> float:
        """
        Normalize number precision.

        This method normalizes a number to a specified number of significant
        digits, preserving the order of magnitude.

        Args:
            number: Numeric value to normalize
            significant_digits: Number of significant digits to preserve

        Returns:
            float: Normalized number with specified significant digits
        """
        if number == 0:
            return 0.0

        # Calculate order of magnitude
        magnitude = abs(number)
        order = 0
        while magnitude >= 10:
            magnitude /= 10
            order += 1
        while magnitude < 1:
            magnitude *= 10
            order -= 1

        # Round to significant digits
        rounded = round(magnitude, significant_digits - 1)

        return rounded * (10**order)
