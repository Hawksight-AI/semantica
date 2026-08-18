import os
import sys
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from semantica.semantic_extract.methods import (
    extract_entities_llm,
    extract_relations_llm,
    extract_triplets_llm,
)
from semantica.semantic_extract.providers import create_provider
from semantica.semantic_extract import Entity

ORCAROUTER_API_KEY = os.environ.get("ORCAROUTER_API_KEY")
ORCAROUTER_MODEL = "openai/gpt-4o"
TEXT = (
    "Apple Inc. was founded by Steve Jobs, Steve Wozniak, and Ronald Wayne in 1976. "
    "It is headquartered in Cupertino, California. The company designs, manufactures, "
    "and markets smartphones, personal computers, tablets, wearables, and accessories."
)

pytestmark = pytest.mark.skipif(
    not ORCAROUTER_API_KEY,
    reason="ORCAROUTER_API_KEY not set",
)


def test_orcarouter_provider_available():
    provider = create_provider("orcarouter")
    assert (
        provider.is_available()
    ), "OrcaRouter provider not available — check ORCAROUTER_API_KEY and openai install"


def test_orcarouter_entity_extraction():
    entities = extract_entities_llm(TEXT, provider="orcarouter", model=ORCAROUTER_MODEL)
    assert isinstance(entities, list), "Expected a list of entities"
    assert len(entities) > 0, "No entities extracted"


def test_orcarouter_relation_extraction():
    sample_entities = [
        Entity(name="Apple Inc.", type="ORGANIZATION"),
        Entity(name="Steve Jobs", type="PERSON"),
    ]
    relations = extract_relations_llm(
        TEXT, entities=sample_entities, provider="orcarouter", model=ORCAROUTER_MODEL
    )
    assert isinstance(relations, list), "Expected a list of relations"


def test_orcarouter_triplet_extraction():
    triplets = extract_triplets_llm(TEXT, provider="orcarouter", model=ORCAROUTER_MODEL)
    assert isinstance(triplets, list), "Expected a list of triplets"
    assert len(triplets) > 0, "No triplets extracted"


def test_orcarouter_chunked_extraction():
    long_text = " ".join([TEXT] * 10)
    entities = extract_entities_llm(
        long_text,
        provider="orcarouter",
        model=ORCAROUTER_MODEL,
        max_text_length=200,
    )
    assert isinstance(
        entities, list
    ), "Expected a list of entities from chunked extraction"
    assert len(entities) > 0, "No entities extracted from chunked text"
