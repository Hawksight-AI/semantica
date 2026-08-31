"""Regression coverage for NER method merge strategies."""

from unittest.mock import patch

import pytest

from semantica.semantic_extract.ner_extractor import NERExtractor
from semantica.semantic_extract.types import Entity


def entity(text, label, start, end, confidence=0.9):
    """Create a compact entity fixture with realistic offsets."""
    return Entity(text, label, start, end, confidence=confidence)


def test_consensus_rejects_single_method_candidate_with_empty_peer():
    """An empty eligible method must remain in the consensus denominator."""
    extractor = NERExtractor(
        method=["first", "second"], merge_strategy="consensus", min_votes=2
    )

    result = extractor._vote_entities(
        [("first", [entity("Apple", "ORG", 0, 5)]), ("second", [])],
        eligible_methods=["first", "second"],
    )

    assert result == []


def test_consensus_aligns_compatible_labels_and_exposes_provenance():
    """Compatible labels vote together and preserve auditable method evidence."""
    extractor = NERExtractor(
        method=["first", "second"], merge_strategy="consensus", min_votes=2
    )

    result = extractor._vote_entities(
        [
            ("first", [entity("Apple", "ORGANIZATION", 0, 5, 0.8)]),
            ("second", [entity("Apple", "ORG", 0, 5, 0.9)]),
        ],
        eligible_methods=["first", "second"],
    )

    assert len(result) == 1
    merged = result[0]
    assert merged.label == "ORG"
    assert merged.confidence == pytest.approx(0.85)
    assert merged.metadata["supporting_methods"] == ["first", "second"]
    assert merged.metadata["vote_count"] == 2
    assert merged.metadata["eligible_method_count"] == 2
    assert merged.metadata["agreement"] == 1.0
    assert merged.metadata["method_scores"] == {"first": 0.8, "second": 0.9}


def test_consensus_keeps_repeated_mentions_at_distinct_offsets():
    """Matching text must not collapse separate document mentions."""
    extractor = NERExtractor(
        method=["first", "second"], merge_strategy="consensus", min_votes=2
    )
    first_mentions = [
        entity("Apple", "ORG", 0, 5),
        entity("Apple", "ORG", 10, 15),
    ]
    second_mentions = [
        entity("Apple", "ORG", 0, 5),
        entity("Apple", "ORG", 10, 15),
    ]

    result = extractor._vote_entities(
        [("first", first_mentions), ("second", second_mentions)],
        eligible_methods=["first", "second"],
    )

    assert [(item.text, item.start_char, item.end_char) for item in result] == [
        ("Apple", 0, 5),
        ("Apple", 10, 15),
    ]


def test_consensus_resolves_boundary_variants_deterministically():
    """Equal-confidence overlapping spans prefer the most specific boundary."""
    extractor = NERExtractor(
        method=["first", "second"], merge_strategy="consensus", min_votes=2
    )

    result = extractor._vote_entities(
        [
            ("first", [entity("Apple", "ORG", 0, 5, 0.9)]),
            ("second", [entity("Apple Inc.", "ORG", 0, 10, 0.9)]),
        ],
        eligible_methods=["first", "second"],
    )

    assert len(result) == 1
    assert (result[0].text, result[0].start_char, result[0].end_char) == (
        "Apple Inc.",
        0,
        10,
    )


def test_consensus_resolves_conflicting_labels_deterministically():
    """With equal vote counts, the higher-confidence label wins predictably."""
    extractor = NERExtractor(
        method=["first", "second"], merge_strategy="consensus", min_votes=1
    )

    result = extractor._vote_entities(
        [
            ("first", [entity("Apple", "ORG", 0, 5, 0.7)]),
            ("second", [entity("Apple", "PRODUCT", 0, 5, 0.9)]),
        ],
        eligible_methods=["first", "second"],
    )

    assert len(result) == 1
    assert result[0].label == "PRODUCT"
    assert result[0].metadata["supporting_methods"] == ["second"]


def test_consensus_prefers_a_same_label_match_over_a_tied_conflict():
    """A conflicting duplicate from one method cannot hide true agreement."""
    extractor = NERExtractor(
        method=["first", "second"], merge_strategy="consensus", min_votes=2
    )

    result = extractor._vote_entities(
        [
            (
                "first",
                [
                    entity("Apple", "PRODUCT", 0, 5),
                    entity("Apple", "ORG", 0, 5),
                ],
            ),
            ("second", [entity("Apple", "ORG", 0, 5)]),
        ],
        eligible_methods=["first", "second"],
    )

    assert len(result) == 1
    assert result[0].label == "ORG"
    assert result[0].metadata["supporting_methods"] == ["first", "second"]


def test_default_consensus_rejects_a_label_conflict_without_two_votes():
    """Different labels do not turn two methods into two votes for either label."""
    extractor = NERExtractor(method=["first", "second"], merge_strategy="consensus")

    result = extractor._vote_entities(
        [
            ("first", [entity("Apple", "ORG", 0, 5)]),
            ("second", [entity("Apple", "PRODUCT", 0, 5)]),
        ],
        eligible_methods=["first", "second"],
    )

    assert result == []


def test_consensus_keeps_a_majority_label_despite_a_high_weight_single_vote():
    """Weights break ties only after the configured vote requirements are met."""
    extractor = NERExtractor(
        method=["first", "second", "third"],
        merge_strategy="consensus",
        min_votes=2,
        method_weights={"third": 100.0},
    )

    result = extractor._vote_entities(
        [
            ("first", [entity("Apple", "ORG", 0, 5, 0.7)]),
            ("second", [entity("Apple", "ORG", 0, 5, 0.7)]),
            ("third", [entity("Apple", "PRODUCT", 0, 5, 0.99)]),
        ],
        eligible_methods=["first", "second", "third"],
    )

    assert len(result) == 1
    assert result[0].label == "ORG"
    assert result[0].metadata["supporting_methods"] == ["first", "second"]


def test_method_weights_treat_ml_and_spacy_as_one_backend():
    """A spaCy alias weight must apply when the configured method is called ml."""
    extractor = NERExtractor(method="pattern", merge_strategy="consensus", min_votes=1)

    result = extractor._vote_entities(
        [
            ("ml", [entity("Apple", "ORG", 0, 5, 0.7)]),
            ("regex", [entity("Apple", "PRODUCT", 0, 5, 0.9)]),
        ],
        eligible_methods=["ml", "regex"],
        min_votes=1,
        method_weights={"spacy": 100.0, "regex": 1.0},
    )

    assert len(result) == 1
    assert result[0].label == "ORG"


def test_method_weights_reject_conflicting_ml_and_spacy_aliases():
    """A single backend cannot receive two different alias weights."""
    with pytest.raises(ValueError, match="conflicting values to aliases"):
        NERExtractor(
            method="pattern",
            merge_strategy="consensus",
            method_weights={"ml": 1.0, "spacy": 2.0},
        )


def test_consensus_does_not_merge_distant_mentions_through_a_broad_span():
    """A broad span below the IoU threshold cannot fabricate cross-method support."""
    extractor = NERExtractor(
        method=["first", "second"], merge_strategy="consensus", min_votes=2
    )

    result = extractor._vote_entities(
        [
            (
                "first",
                [
                    entity("A B", "ORG", 0, 3),
                    entity("C D", "ORG", 4, 7),
                ],
            ),
            ("second", [entity("A B C D", "ORG", 0, 7)]),
        ],
        eligible_methods=["first", "second"],
    )

    assert result == []


def test_consensus_requires_each_vote_to_overlap_every_other_vote():
    """A chain of pairwise overlaps must not fabricate three-way support."""
    extractor = NERExtractor(
        method=["first", "second", "third"],
        merge_strategy="consensus",
        min_votes=3,
    )

    result = extractor._vote_entities(
        [
            ("first", [entity("ABCD", "ORG", 0, 4)]),
            ("second", [entity("ABCDEF", "ORG", 0, 6)]),
            ("third", [entity("CDEF", "ORG", 2, 6)]),
        ],
        eligible_methods=["first", "second", "third"],
    )

    assert result == []


def test_consensus_prefers_an_exact_boundary_match_within_one_method_batch():
    """A weaker overlap cannot consume another method's exact boundary vote."""
    extractor = NERExtractor(
        method=["first", "second"], merge_strategy="consensus", min_votes=2
    )

    result = extractor._vote_entities(
        [
            (
                "first",
                [
                    entity("Apple", "ORG", 0, 5, 0.99),
                    entity("Apple Inc.", "ORG", 0, 10, 0.1),
                ],
            ),
            ("second", [entity("Apple Inc.", "ORG", 0, 10, 0.9)]),
        ],
        eligible_methods=["first", "second"],
    )

    assert len(result) == 1
    assert (result[0].start_char, result[0].end_char) == (0, 10)
    assert result[0].metadata["supporting_methods"] == ["first", "second"]


def test_consensus_boundary_result_is_independent_of_method_result_order():
    """Method result order cannot affect the selected consensus boundary."""
    extractor = NERExtractor(
        method=["first", "second"], merge_strategy="consensus", min_votes=2
    )
    first = [
        entity("Apple", "ORG", 0, 5, 0.99),
        entity("Apple Inc.", "ORG", 0, 10, 0.1),
    ]
    second = [entity("Apple Inc.", "ORG", 0, 10, 0.9)]

    forward = extractor._vote_entities(
        [("first", first), ("second", second)],
        eligible_methods=["first", "second"],
    )
    reverse = extractor._vote_entities(
        [("second", second), ("first", list(reversed(first)))],
        eligible_methods=["first", "second"],
    )

    assert [
        (item.label, item.start_char, item.end_char, item.metadata) for item in reverse
    ] == [
        (item.label, item.start_char, item.end_char, item.metadata) for item in forward
    ]


def test_consensus_keeps_nested_entities_with_different_labels():
    """Exact-span label arbitration must not erase a nested entity."""
    extractor = NERExtractor(
        method=["first", "second"], merge_strategy="consensus", min_votes=2
    )
    mentions = [
        entity("New York", "GPE", 0, 8),
        entity("New York Times", "ORG", 0, 14),
    ]

    result = extractor._vote_entities(
        [("first", mentions), ("second", mentions)],
        eligible_methods=["first", "second"],
    )

    assert [(item.label, item.start_char, item.end_char) for item in result] == [
        ("GPE", 0, 8),
        ("ORG", 0, 14),
    ]


def test_union_keeps_complementary_single_method_entities():
    """Explicit union preserves the legacy complementary-method behavior."""
    extractor = NERExtractor(method=["first", "second"], merge_strategy="union")

    result = extractor._union_entities(
        [("first", [entity("SKU-12345", "PRODUCT_CODE", 10, 19)]), ("second", [])],
        eligible_methods=["first", "second"],
    )

    assert [(item.text, item.label) for item in result] == [
        ("SKU-12345", "PRODUCT_CODE")
    ]
    assert result[0].metadata["vote_count"] == 1
    assert result[0].metadata["agreement"] == 0.5


def test_union_preserves_distinct_labels_and_original_label_spelling():
    """Union is complementary: it does not force label-conflict resolution."""
    extractor = NERExtractor(method=["first", "second"], merge_strategy="union")

    result = extractor._union_entities(
        [
            ("first", [entity("Apple", "ORG", 0, 5)]),
            ("second", [entity("Apple", "PRODUCT", 0, 5)]),
        ],
        eligible_methods=["first", "second"],
    )

    assert [(item.text, item.label) for item in result] == [
        ("Apple", "ORG"),
        ("Apple", "PRODUCT"),
    ]


def test_ml_and_spacy_aliases_do_not_duplicate_an_entity_or_a_vote():
    """Two names for spaCy represent one backend, not independent voters."""
    extractor = NERExtractor(method=["ml", "spacy"], merge_strategy="union")

    result = extractor._union_entities(
        [
            ("ml", [entity("Apple", "ORG", 0, 5)]),
            ("spacy", [entity("Apple", "ORG", 0, 5)]),
        ],
        eligible_methods=["ml", "spacy"],
    )

    assert len(result) == 1
    assert result[0].metadata["supporting_methods"] == ["ml"]
    assert result[0].metadata["eligible_method_count"] == 1


def test_extract_consensus_counts_a_successful_empty_method():
    """The public extraction path must retain empty method results for voting."""
    extractor = NERExtractor(
        method=["pattern", "regex"], merge_strategy="consensus", min_votes=2
    )
    responses = {"pattern": [entity("Apple", "ORG", 0, 5)], "regex": []}

    with patch(
        "semantica.semantic_extract.methods.get_entity_method",
        side_effect=lambda method_name: (
            lambda _text, **_options: responses[method_name]
        ),
    ):
        assert extractor.extract_entities("Apple") == []


def test_extract_consensus_keeps_method_provenance_on_a_successful_vote():
    """Public extraction must retain method names for provenance."""
    extractor = NERExtractor(
        method=["pattern", "regex"], merge_strategy="consensus", min_votes=2
    )
    responses = {
        "pattern": [entity("Apple", "ORG", 0, 5, 0.8)],
        "regex": [entity("Apple", "ORGANIZATION", 0, 5, 0.9)],
    }

    with patch(
        "semantica.semantic_extract.methods.get_entity_method",
        side_effect=lambda method_name: lambda _text, **_options: responses[
            method_name
        ],
    ):
        result = extractor.extract_entities("Apple")

    assert len(result) == 1
    assert result[0].metadata["supporting_methods"] == ["pattern", "regex"]
    assert result[0].metadata["method_scores"] == {"pattern": 0.8, "regex": 0.9}


def test_merge_options_are_not_forwarded_to_custom_methods():
    """Custom methods without **kwargs remain usable with the new merge API."""
    extractor = NERExtractor(
        method=["first", "second"], merge_strategy="consensus", min_votes=2
    )
    responses = {
        "first": [entity("Apple", "ORG", 0, 5)],
        "second": [entity("Apple", "ORG", 0, 5)],
    }

    with patch(
        "semantica.semantic_extract.methods.get_entity_method",
        side_effect=lambda method_name: lambda _text: responses[method_name],
    ):
        result = extractor.extract_entities("Apple")

    assert len(result) == 1


def test_legacy_options_remain_available_to_custom_methods():
    """Existing custom methods retain the legacy options they previously received."""
    with pytest.warns(DeprecationWarning, match="ensemble_voting"):
        extractor = NERExtractor(
            method="custom", ensemble_voting=True, post_process=True
        )
    received = {}

    def custom_method(_text, *, ensemble_voting, post_process):
        received.update(
            ensemble_voting=ensemble_voting,
            post_process=post_process,
        )
        return [entity("Apple", "ORG", 0, 5)]

    with patch(
        "semantica.semantic_extract.methods.get_entity_method",
        return_value=custom_method,
    ):
        result = extractor.extract_entities("Apple")

    assert len(result) == 1
    assert received == {"ensemble_voting": True, "post_process": True}


def test_extract_consensus_recovers_missing_llm_offsets_before_voting():
    """Typed LLM results with schema-default 0:0 spans can still vote safely."""
    extractor = NERExtractor(
        method=["llm", "regex"], merge_strategy="consensus", min_votes=2
    )
    responses = {
        "llm": [entity("Apple", "ORG", 0, 0, 0.9)],
        "regex": [entity("Apple", "ORG", 0, 5, 0.8)],
    }

    with patch(
        "semantica.semantic_extract.methods.get_entity_method",
        side_effect=lambda method_name: lambda _text, **_options: responses[
            method_name
        ],
    ):
        result = extractor.extract_entities("Apple")

    assert len(result) == 1
    assert (result[0].start_char, result[0].end_char) == (0, 5)
    assert result[0].metadata["supporting_methods"] == ["llm", "regex"]


def test_missing_offsets_are_assigned_to_distinct_repeated_mentions():
    """Text-only duplicate output is aligned in occurrence order before merging."""
    extractor = NERExtractor(method="llm", merge_strategy="union")

    aligned = extractor._align_entities_to_text(
        [
            entity("Apple", "ORG", 0, 0),
            entity("Apple", "ORG", 0, 0),
        ],
        "Apple and Apple",
    )

    assert [(item.start_char, item.end_char) for item in aligned] == [(0, 5), (10, 15)]


def test_missing_offsets_wrap_to_an_unoccupied_repeated_mention():
    """A valid later mention must not make an earlier missing one unalignable."""
    extractor = NERExtractor(method="llm", merge_strategy="union")

    aligned = extractor._align_entities_to_text(
        [
            entity("Apple", "ORG", 10, 15),
            entity("Apple", "ORG", 0, 0),
        ],
        "Apple and Apple",
    )

    assert [(item.start_char, item.end_char) for item in aligned] == [(10, 15), (0, 5)]


def test_missing_offsets_do_not_align_a_substring_inside_a_larger_word():
    """Offset recovery must not let Apple vote for the substring in Pineapple."""
    extractor = NERExtractor(
        method=["llm", "regex"], merge_strategy="consensus", min_votes=2
    )
    responses = {
        "llm": [entity("Apple", "ORG", 0, 0, 0.9)],
        "regex": [entity("Pineapple", "ORG", 0, 9, 0.8)],
    }

    with patch(
        "semantica.semantic_extract.methods.get_entity_method",
        side_effect=lambda method_name: lambda _text, **_options: responses[
            method_name
        ],
    ):
        assert extractor.extract_entities("Pineapple") == []


def test_missing_offsets_preserve_original_unicode_character_positions():
    """Case-insensitive matching preserves original Unicode offsets."""
    extractor = NERExtractor(method="llm", merge_strategy="union")

    aligned = extractor._align_entities_to_text(
        [entity("Apple", "ORG", 0, 0)],
        "İ Apple",
    )

    assert [(item.start_char, item.end_char) for item in aligned] == [(2, 7)]


def test_consensus_eligible_methods_can_exclude_complementary_extractors():
    """An explicit eligible subset controls the denominator used for agreement."""
    extractor = NERExtractor(
        method=["first", "second", "supplement"],
        merge_strategy="consensus",
        min_votes=2,
        min_agreement=0.75,
        eligible_methods=["first", "second"],
    )
    responses = {
        "first": [entity("Apple", "ORG", 0, 5)],
        "second": [entity("Apple", "ORG", 0, 5)],
        "supplement": [],
    }

    with patch(
        "semantica.semantic_extract.methods.get_entity_method",
        side_effect=lambda method_name: lambda _text, **_options: responses[
            method_name
        ],
    ):
        result = extractor.extract_entities("Apple")

    assert len(result) == 1
    assert result[0].metadata["eligible_method_count"] == 2
    assert result[0].metadata["agreement"] == 1.0


def test_extract_consensus_does_not_inject_fallback_candidates():
    """An all-empty consensus result must remain empty rather than fall back."""
    extractor = NERExtractor(
        method=["pattern", "regex"], merge_strategy="consensus", min_votes=2
    )

    with patch(
        "semantica.semantic_extract.methods.get_entity_method",
        side_effect=lambda _method_name: lambda _text, **_options: [],
    ):
        assert extractor.extract_entities("Apple") == []


def test_consensus_counts_a_failed_eligible_method_in_agreement():
    """A failed configured method is non-supporting rather than silently removed."""
    extractor = NERExtractor(
        method=["pattern", "regex"],
        merge_strategy="consensus",
        min_votes=1,
        min_agreement=0.75,
    )

    def method_for(method_name):
        if method_name == "pattern":
            return lambda _text, **_options: [entity("Apple", "ORG", 0, 5)]
        return lambda _text, **_options: (_ for _ in ()).throw(RuntimeError("offline"))

    with patch(
        "semantica.semantic_extract.methods.get_entity_method",
        side_effect=method_for,
    ):
        assert extractor.extract_entities("Apple") == []


def test_union_ignores_consensus_eligible_method_subset():
    """Complementary union must retain all methods even when consensus is scoped."""
    extractor = NERExtractor(
        method=["pattern", "regex"],
        merge_strategy="union",
        eligible_methods=["pattern"],
    )
    responses = {
        "pattern": [entity("Apple", "ORG", 0, 5)],
        "regex": [entity("SKU-12345", "PRODUCT_CODE", 10, 19)],
    }

    with patch(
        "semantica.semantic_extract.methods.get_entity_method",
        side_effect=lambda method_name: lambda _text, **_options: responses[
            method_name
        ],
    ):
        result = extractor.extract_entities("Apple SKU-12345")

    assert [(item.text, item.label) for item in result] == [
        ("Apple", "ORG"),
        ("SKU-12345", "PRODUCT_CODE"),
    ]


def test_issue_1283_consensus_requires_cross_method_agreement():
    """The former ensemble union must not be mistaken for consensus."""
    responses = {
        "first": [entity("Apple", "ORG", 0, 5)],
        "second": [entity("SKU-12345", "PRODUCT_CODE", 6, 15)],
    }

    with patch(
        "semantica.semantic_extract.methods.get_entity_method",
        side_effect=lambda method_name: lambda _text, **_options: responses[
            method_name
        ],
    ):
        with pytest.warns(DeprecationWarning, match="ensemble_voting"):
            legacy = NERExtractor(method=["first", "second"], ensemble_voting=True)
        consensus = NERExtractor(
            method=["first", "second"],
            merge_strategy="consensus",
            min_votes=2,
        )

        legacy_entities = legacy.extract_entities("Apple SKU-12345")
        consensus_entities = consensus.extract_entities("Apple SKU-12345")

    assert [(item.text, item.label) for item in legacy_entities] == [
        ("Apple", "ORG"),
        ("SKU-12345", "PRODUCT_CODE"),
    ]
    assert consensus_entities == []


def test_fallback_remains_first_nonempty_method():
    """The default strategy remains the documented ordered fallback chain."""
    extractor = NERExtractor(method=["first", "second"], merge_strategy="fallback")
    responses = {"first": [], "second": [entity("Apple", "ORG", 0, 5)]}

    with patch(
        "semantica.semantic_extract.methods.get_entity_method",
        side_effect=lambda method_name: (
            lambda _text, **_options: responses[method_name]
        ),
    ):
        result = extractor.extract_entities("Apple")

    assert [(item.text, item.label) for item in result] == [("Apple", "ORG")]


def test_default_strategy_short_circuits_at_the_first_nonempty_method():
    """No merge strategy keeps the public ordered fallback behavior unchanged."""
    extractor = NERExtractor(method=["first", "second"])
    requested_methods = []
    responses = {
        "first": [entity("Apple", "ORG", 0, 5)],
        "second": [entity("SKU-12345", "PRODUCT_CODE", 6, 15)],
    }

    def method_for(method_name):
        requested_methods.append(method_name)
        return lambda _text, **_options: responses[method_name]

    with patch(
        "semantica.semantic_extract.methods.get_entity_method",
        side_effect=method_for,
    ):
        result = extractor.extract_entities("Apple SKU-12345")

    assert [(item.text, item.label) for item in result] == [("Apple", "ORG")]
    assert requested_methods == ["first"]


def test_legacy_ensemble_flag_maps_to_deprecated_union_strategy():
    """Existing callers keep their union behavior while receiving migration guidance."""
    with pytest.warns(DeprecationWarning, match="ensemble_voting"):
        extractor = NERExtractor(method=["first", "second"], ensemble_voting=True)

    assert extractor.merge_strategy == "union"


def test_legacy_ensemble_flag_still_runs_the_union_path():
    """The deprecated flag retains single-method candidates during migration."""
    with pytest.warns(DeprecationWarning, match="ensemble_voting"):
        extractor = NERExtractor(method=["first", "second"], ensemble_voting=True)
    responses = {
        "first": [entity("Apple", "ORG", 0, 5)],
        "second": [entity("SKU-12345", "PRODUCT_CODE", 6, 15)],
    }

    with patch(
        "semantica.semantic_extract.methods.get_entity_method",
        side_effect=lambda method_name: lambda _text, **_options: responses[
            method_name
        ],
    ):
        result = extractor.extract_entities("Apple SKU-12345")

    assert [(item.text, item.label) for item in result] == [
        ("Apple", "ORG"),
        ("SKU-12345", "PRODUCT_CODE"),
    ]
