from semantica.kg.entity_resolver import EntityResolver


def test_exact_resolution_does_not_merge_similar_names():
    entities = [
        {"id": "1", "name": "Alice"},
        {"id": "2", "name": "Alicia"},
    ]

    resolved = EntityResolver(strategy="exact").resolve_entities(entities)

    assert {entity["id"] for entity in resolved} == {"1", "2"}


def test_exact_resolution_merges_case_and_whitespace_variants():
    entities = [
        {"id": "1", "name": " Alice "},
        {"id": "2", "name": "alice"},
    ]

    resolved = EntityResolver(strategy="exact").resolve_entities(entities)

    assert len(resolved) == 1


def test_resolution_preserves_non_duplicate_entities_without_ids():
    entities = [
        {"name": "Alice"},
        {"name": "Bob"},
    ]

    resolved = EntityResolver(strategy="exact").resolve_entities(entities)

    assert resolved == entities


def test_exact_resolution_does_not_merge_whitespace_only_names():
    entities = [
        {"id": "1", "name": "   "},
        {"id": "2", "name": "\t"},
    ]

    resolved = EntityResolver(strategy="exact").resolve_entities(entities)

    assert {entity["id"] for entity in resolved} == {"1", "2"}


def test_exact_resolution_falls_back_to_text_when_name_is_blank():
    entities = [
        {"id": "1", "name": " ", "text": "Alice"},
        {"id": "2", "name": "Alice"},
    ]

    resolved = EntityResolver(strategy="exact").resolve_entities(entities)

    assert len(resolved) == 1
