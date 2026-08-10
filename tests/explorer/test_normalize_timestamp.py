"""Unit tests for _normalize_timestamp hardening (PR #887 review findings).

Covers the two Qodo review findings:
1. Numeric epochs must not raise on malformed input (NaN/inf/out-of-range)
   — the helper contract says it returns None for unrecognized values.
2. datetime inputs must be normalized to UTC (ISO 8601 with offset), not
   returned as-is (which can be naive or non-UTC).
"""
import math
from datetime import datetime, timezone, timedelta

import pytest

from semantica.explorer.routes.decisions import _normalize_timestamp


class TestNumericEpochHardening:
    def test_valid_epoch_converts_to_iso_utc(self):
        # 2026-08-10T12:00:00Z
        value = 1786262400.0
        result = _normalize_timestamp(value)
        assert result is not None
        parsed = datetime.fromisoformat(result)
        assert parsed.tzinfo is not None
        assert parsed.utcoffset() == timedelta(0)

    def test_nan_returns_none_not_raise(self):
        assert _normalize_timestamp(float("nan")) is None

    def test_inf_returns_none_not_raise(self):
        assert _normalize_timestamp(float("inf")) is None
        assert _normalize_timestamp(float("-inf")) is None

    def test_out_of_range_epoch_returns_none_not_raise(self):
        # Way beyond datetime.max (year 9999)
        assert _normalize_timestamp(10**20) is None

    def test_negative_epoch_converts(self):
        # Negative epochs are valid (pre-1970)
        result = _normalize_timestamp(-86400.0)
        assert result is not None
        parsed = datetime.fromisoformat(result)
        assert parsed.year < 1970


class TestDatetimeUtcNormalization:
    def test_naive_datetime_assumed_utc(self):
        value = datetime(2026, 8, 10, 12, 0, 0)  # naive
        result = _normalize_timestamp(value)
        assert result is not None
        parsed = datetime.fromisoformat(result)
        assert parsed.tzinfo is not None
        assert parsed.utcoffset() == timedelta(0)
        assert parsed.hour == 12  # assumed UTC, unchanged wall time

    def test_non_utc_datetime_converted_to_utc(self):
        value = datetime(2026, 8, 10, 15, 0, 0, tzinfo=timezone(timedelta(hours=3)))
        result = _normalize_timestamp(value)
        assert result is not None
        parsed = datetime.fromisoformat(result)
        assert parsed.utcoffset() == timedelta(0)
        assert parsed.hour == 12  # 15:00+03:00 -> 12:00Z

    def test_utc_datetime_unchanged(self):
        value = datetime(2026, 8, 10, 12, 0, 0, tzinfo=timezone.utc)
        result = _normalize_timestamp(value)
        parsed = datetime.fromisoformat(result)
        assert parsed == value


class TestOtherInputs:
    def test_none_passthrough(self):
        assert _normalize_timestamp(None) is None

    def test_string_passthrough(self):
        assert _normalize_timestamp("2026-08-10T12:00:00Z") == "2026-08-10T12:00:00Z"

    def test_unrecognized_type_returns_none(self):
        assert _normalize_timestamp({"nested": True}) is None
        assert _normalize_timestamp([]) is None
