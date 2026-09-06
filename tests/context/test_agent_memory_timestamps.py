"""Timestamp semantics for AgentMemory (#found-by-audit).

MemoryItem timestamps had two producers with different naive conventions:
``add()`` defaulted to ``datetime.now()`` (naive LOCAL) while ``from_dict``
fell back to ``datetime.utcnow()`` (naive UTC). ``_timestamp_comparison_key``
interprets every naive stamp as LOCAL time, so on any host off UTC the two
producers disagree by the host's offset — a UTC+8 host pushed freshly added
memories 8 hours outside every ``start_date``/``end_date`` window, and
``cleanup_old_memories`` aged them wrong by the same amount.

The contract pinned here:

* every NEW stamp the module produces is timezone-aware UTC;
* legacy naive stamps keep their documented local-time meaning through the
  comparison key (it must not flip to interpreting naive as UTC);
* aware stamps compare correctly against naive and aware boundaries alike,
  on hosts in any timezone.
"""

import sys
import os
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from semantica.context.agent_memory import AgentMemory, MemoryItem


def host_offset() -> timedelta:
    return datetime.now().astimezone().utcoffset() or timedelta(0)


class TestAwareUtcProducers(unittest.TestCase):
    def test_add_default_timestamp_is_aware_utc(self):
        memory = AgentMemory()
        memory.store("recall me")

        item = next(iter(memory.memory_items.values()))
        self.assertIsNotNone(item.timestamp.tzinfo, "add() must not produce naive stamps")
        self.assertEqual(item.timestamp.utcoffset(), timedelta(0), "add() must stamp UTC, not local")

    def test_from_dict_missing_timestamp_is_aware_utc(self):
        item = MemoryItem.from_dict({"content": "reconstructed"})
        self.assertIsNotNone(item.timestamp.tzinfo)
        self.assertEqual(item.timestamp.utcoffset(), timedelta(0))

    def test_round_trip_preserves_the_instant(self):
        memory = AgentMemory()
        memory.store("persisted")
        original = next(iter(memory.memory_items.values()))

        restored = MemoryItem.from_dict(original.to_dict())

        self.assertEqual(
            restored.timestamp,
            original.timestamp,
            "isoformat() must round-trip the exact instant for the comparison key to stay truthful",
        )


class TestComparisonKeySemantics(unittest.TestCase):
    def test_naive_stamps_keep_their_local_time_meaning(self):
        # _timestamp_comparison_key documents naive-as-local. If it silently
        # flips to naive-as-UTC, every legacy persisted stamp shifts by the
        # host offset — the same class of drift this file exists for, in the
        # other direction.
        naive = datetime(2026, 1, 1, 12, 0, 0)
        self.assertEqual(
            AgentMemory._timestamp_comparison_key(naive),
            naive.astimezone(timezone.utc),
        )

    def test_aware_utc_stamp_is_not_shifted(self):
        aware = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        self.assertEqual(
            AgentMemory._timestamp_comparison_key(aware),
            aware,
        )


class TestDateRangeFiltering(unittest.TestCase):
    def test_freshly_added_memory_is_inside_a_utc_window_around_now(self):
        # The regression, end to end: a memory added "now" must land inside a
        # start_date/end_date window expressed in UTC around now. With the
        # naive-local producer this fails by exactly the host offset on every
        # non-UTC host.
        memory = AgentMemory()
        memory.store("window probe")
        now = datetime.now(timezone.utc)

        results = memory.retrieve(
            "probe",
            max_results=10,
            start_date=(now - timedelta(minutes=5)).isoformat(),
            end_date=(now + timedelta(minutes=5)).isoformat(),
        )

        self.assertTrue(
            any(r.get("content") == "window probe" for r in results),
            f"memory added now must be within the UTC window (host offset {host_offset()})",
        )

    def test_explicit_utc_boundary_excludes_older_stamps(self):
        memory = AgentMemory()
        old = datetime(2020, 1, 1, tzinfo=timezone.utc)
        memory.store("old memory", timestamp=old)
        boundary = datetime(2025, 1, 1, tzinfo=timezone.utc)

        results = memory.retrieve(
            "memory",
            max_results=10,
            start_date=boundary.isoformat(),
        )

        self.assertFalse(
            any(r.get("content") == "old memory" for r in results),
            "a 2020 stamp must not match a window starting in 2025, whatever the host timezone",
        )


if __name__ == "__main__":
    unittest.main()
