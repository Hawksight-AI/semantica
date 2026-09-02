"""AgentMemory.find_by_entity returns all matches by default (#1018).

The previous default limit of 10 silently truncated results, making erasure
workflows incomplete for entities with more than 10 memories: a caller
computing "what references this entity" from a truncated page would leave
the remainder live. The unbounded default is deliberate — an erasure check
cannot paginate — while callers that want a page still pass an explicit
limit. (Previously lived in tests/test_seed_manager.py; moved to the
AgentMemory area per review.)
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from semantica.context.agent_memory import AgentMemory


@pytest.fixture
def memory_with_15():
    mem = AgentMemory()
    for i in range(15):
        mem.store(
            content=f"fact {i} about entity",
            entities=[{"id": "e1", "name": "Entity", "type": "thing"}],
        )
    return mem


class TestFindByEntityLimit:
    def test_returns_all_matches_by_default(self, memory_with_15):
        results = memory_with_15.find_by_entity("e1")
        assert len(results) == 15, f"expected 15 (all), got {len(results)}"

    def test_explicit_limit_still_works(self, memory_with_15):
        assert len(memory_with_15.find_by_entity("e1", limit=5)) == 5

    def test_no_matches_returns_empty(self):
        assert AgentMemory().find_by_entity("nonexistent") == []
