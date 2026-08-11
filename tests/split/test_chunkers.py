"""Tests for previously untested split chunker classes (issue #864)."""

import pytest

from semantica.split.kg_chunkers import (
    EntityAwareChunker,
    GraphBasedChunker,
    HierarchicalChunker,
    OntologyAwareChunker,
    RelationAwareChunker,
)
from semantica.split.methods import (
    SEMANTIC_EXTRACT_AVAILABLE,
    NETWORKX_AVAILABLE,
    split_by_characters,
    split_by_paragraphs,
    split_by_sentences,
    split_by_words,
    split_entity_aware,
    split_graph_based,
    split_hierarchical,
    split_ontology_aware,
    split_recursive,
    split_relation_aware,
    split_sliding_window,
    split_structural,
)
from semantica.split.semantic_chunker import Chunk
from semantica.split.sliding_window_chunker import SlidingWindowChunker
from semantica.split.structural_chunker import StructuralChunker, StructuralElement
from semantica.split.table_chunker import TableChunk, TableChunker
from semantica.utils.exceptions import ValidationError

requires_semantic_extract = pytest.mark.skipif(
    not SEMANTIC_EXTRACT_AVAILABLE,
    reason="semantica.semantic_extract is not available",
)
requires_networkx = pytest.mark.skipif(
    not NETWORKX_AVAILABLE,
    reason="networkx is not available",
)


# ---------------------------------------------------------------------------
# SlidingWindowChunker
# ---------------------------------------------------------------------------


class TestSlidingWindowChunker:
    def test_init_defaults_and_validation(self):
        chunker = SlidingWindowChunker(chunk_size=100, overlap=20)
        assert chunker.chunk_size == 100
        assert chunker.overlap == 20
        assert chunker.stride == 80

        with pytest.raises(ValidationError):
            SlidingWindowChunker(chunk_size=0)
        with pytest.raises(ValidationError):
            SlidingWindowChunker(chunk_size=100, overlap=-1)
        with pytest.raises(ValidationError):
            SlidingWindowChunker(chunk_size=100, overlap=100)

    def test_empty_text_returns_empty(self):
        chunker = SlidingWindowChunker(chunk_size=50, overlap=10)
        assert chunker.chunk("") == []

    def test_fixed_size_overlap_invariant(self):
        """Last `overlap` chars of chunk N appear at the start of chunk N+1."""
        text = "abcdefghijklmnopqrstuvwxyz0123456789" * 3  # 108 chars
        overlap = 10
        chunk_size = 30
        chunker = SlidingWindowChunker(
            chunk_size=chunk_size, overlap=overlap, stride=chunk_size - overlap
        )
        chunks = chunker.chunk(text, preserve_boundaries=False)

        assert len(chunks) >= 2
        for i in range(len(chunks) - 1):
            # Final chunk may be shorter than overlap; compare shared window only
            shared = min(overlap, len(chunks[i].text), len(chunks[i + 1].text))
            expected_overlap = chunks[i].text[-shared:]
            actual_prefix = chunks[i + 1].text[:shared]
            assert actual_prefix == expected_overlap, (
                f"Overlap mismatch between chunk {i} and {i + 1}: "
                f"{expected_overlap!r} != {actual_prefix!r}"
            )

        for i in range(len(chunks) - 1):
            assert (
                chunks[i + 1].start_index - chunks[i].start_index
                == chunk_size - overlap
            )

    def test_chunk_with_overlap_helper(self):
        text = "word " * 40
        chunker = SlidingWindowChunker(chunk_size=50, overlap=0)
        chunks = chunker.chunk_with_overlap(text, overlap_size=15)
        assert len(chunks) >= 2
        assert chunker.overlap == 0

    def test_boundary_preservation_avoids_mid_word_when_possible(self):
        text = (
            "Alice went to the market. Bob bought apples. "
            "Carol cooked dinner. Dave drove home."
        )
        chunker = SlidingWindowChunker(chunk_size=40, overlap=10)
        chunks = chunker.chunk(text, preserve_boundaries=True)
        assert len(chunks) >= 1
        for chunk in chunks:
            assert isinstance(chunk, Chunk)
            assert chunk.text
            assert chunk.metadata.get("chunk_index") is not None


# ---------------------------------------------------------------------------
# StructuralChunker
# ---------------------------------------------------------------------------


class TestStructuralChunker:
    MARKDOWN_DOC = """# Introduction

This is the intro paragraph about the project.

## Details

Here are more details about how it works.

- item one
- item two
- item three

## Conclusion

Final thoughts on the subject.
"""

    def test_empty_text_returns_empty(self):
        chunker = StructuralChunker(max_chunk_size=500)
        assert chunker.chunk("") == []

    def test_heading_based_splits(self):
        chunker = StructuralChunker(respect_headers=True, max_chunk_size=200)
        chunks = chunker.chunk(self.MARKDOWN_DOC)

        assert len(chunks) >= 1
        for chunk in chunks:
            assert isinstance(chunk, Chunk)
            assert chunk.metadata.get("structure_preserved") is True
            assert "element_types" in chunk.metadata

        all_types = []
        for chunk in chunks:
            all_types.extend(chunk.metadata["element_types"])
        assert "heading" in all_types
        assert "paragraph" in all_types

    def test_heading_boundaries_separate_sections(self):
        """Distinct top-level headings must not be merged into one chunk."""
        doc = """# Alpha

Content exclusively about alpha topic here.

# Beta

Content exclusively about beta topic here.
"""
        chunker = StructuralChunker(respect_headers=True, max_chunk_size=50)
        chunks = chunker.chunk(doc)

        assert len(chunks) >= 2
        alpha_chunks = [c for c in chunks if "exclusively about alpha" in c.text]
        beta_chunks = [c for c in chunks if "exclusively about beta" in c.text]
        assert alpha_chunks, "Alpha section body missing from chunks"
        assert beta_chunks, "Beta section body missing from chunks"

        # Heading-boundary invariant: alpha and beta bodies stay in separate chunks
        for chunk in chunks:
            has_alpha = "exclusively about alpha" in chunk.text
            has_beta = "exclusively about beta" in chunk.text
            assert not (has_alpha and has_beta), (
                f"Sections merged across heading boundary: {chunk.text!r}"
            )

    def test_extract_structure_detects_headings_and_lists(self):
        chunker = StructuralChunker()
        elements = chunker._extract_structure(self.MARKDOWN_DOC)
        types = [e.type for e in elements]
        assert "heading" in types
        assert "list" in types
        assert "paragraph" in types
        assert all(isinstance(e, StructuralElement) for e in elements)

    def test_code_block_preserved(self):
        text = """# Code

```python
def hello():
    return "world"
```

After the code.
"""
        chunker = StructuralChunker(max_chunk_size=2000)
        elements = chunker._extract_structure(text)
        types = [e.type for e in elements]
        assert "code_block" in types
        code = next(e for e in elements if e.type == "code_block")
        assert "def hello" in code.text


# ---------------------------------------------------------------------------
# TableChunker
# ---------------------------------------------------------------------------


class TestTableChunker:
    def _sample_table(self, n_rows: int = 10):
        headers = ["Name", "Age", "City"]
        rows = [[f"Person{i}", str(20 + i), f"City{i}"] for i in range(n_rows)]
        return {"headers": headers, "rows": rows}

    def test_rows_are_not_split_mid_row(self):
        """Each chunk contains complete rows only — never a partial row."""
        table = self._sample_table(10)
        chunker = TableChunker(max_rows=3, preserve_headers=True)
        chunks = chunker.chunk_table(table)

        assert len(chunks) == 4  # 3+3+3+1
        for chunk in chunks:
            assert isinstance(chunk, TableChunk)
            assert chunk.headers == ["Name", "Age", "City"]
            for row in chunk.rows:
                assert len(row) == 3
            assert chunk.metadata["row_count"] == len(chunk.rows)

        flattened = [row for c in chunks for row in c.rows]
        assert flattened == table["rows"]

    def test_markdown_table_chunk_does_not_split_rows(self):
        md = """| Name | Age | City |
| --- | --- | --- |
| Alice | 30 | NYC |
| Bob | 25 | LA |
| Carol | 40 | SF |
| Dave | 35 | CHI |
"""
        chunker = TableChunker(max_rows=2, preserve_headers=True)
        chunks = chunker.chunk(md)

        assert len(chunks) == 2
        for chunk in chunks:
            assert chunk.metadata["chunk_type"] == "table"
            data_lines = [
                line
                for line in chunk.text.split("\n")
                if line and "---" not in line and not line.startswith("Name")
            ]
            for line in data_lines:
                cells = [c.strip() for c in line.split("|")]
                assert len(cells) == 3

    def test_non_table_text_returns_single_chunk(self):
        chunker = TableChunker()
        chunks = chunker.chunk("Just plain text without a table.")
        assert len(chunks) == 1
        assert chunks[0].metadata.get("error") == "No table found"

    def test_extract_table_schema(self):
        table = {
            "headers": ["id", "active", "label"],
            "rows": [
                ["1", "true", "alpha"],
                ["2", "false", "beta"],
            ],
        }
        schema = TableChunker().extract_table_schema(table)
        assert schema["column_count"] == 3
        assert schema["row_count"] == 2
        assert schema["column_types"]["id"] == "numeric"
        assert schema["column_types"]["active"] == "boolean"
        assert schema["column_types"]["label"] == "text"

    def test_chunk_by_columns(self):
        table = self._sample_table(3)
        chunker = TableChunker(chunk_by_columns=True, preserve_headers=True)
        chunks = chunker.chunk_table(table, max_columns=2)
        assert len(chunks) == 2
        assert chunks[0].headers == ["Name", "Age"]
        assert chunks[1].headers == ["City"]
        for chunk in chunks:
            for row in chunk.rows:
                assert len(row) == len(chunk.headers)


# ---------------------------------------------------------------------------
# EntityAwareChunker (real optional deps via importorskip / skipif)
# ---------------------------------------------------------------------------


class TestEntityAwareChunker:
    def test_init(self):
        chunker = EntityAwareChunker(
            chunk_size=500, chunk_overlap=50, ner_method="pattern"
        )
        assert chunker.chunk_size == 500
        assert chunker.ner_method == "pattern"
        assert chunker.preserve_entities is True

    def test_empty_text(self):
        chunker = EntityAwareChunker(chunk_size=100, ner_method="pattern")
        chunks = chunker.chunk("")
        assert isinstance(chunks, list)

    @requires_semantic_extract
    def test_entity_boundaries_preserved_with_pattern_ner(self):
        """Entity spans stay intact when using real pattern NER."""
        pytest.importorskip("semantica.semantic_extract")
        entity_text = "AppleInc"
        # Use a contiguous token the pattern NER can latch onto
        text = (
            "Intro sentence one goes here. Intro sentence two goes here. "
            f"{entity_text} was founded in Cupertino California recently. "
            "More filler sentences keep the document long enough to chunk. "
            "Yet another sentence about products and services worldwide. "
            "Final sentence for padding the overall document length out."
        )
        chunks = split_entity_aware(
            text,
            chunk_size=90,
            ner_method="pattern",
            preserve_entities=True,
        )
        assert len(chunks) >= 1
        containing = [c for c in chunks if entity_text in c.text]
        assert containing, "Expected entity text to appear in at least one chunk"
        for chunk in containing:
            idx = chunk.text.index(entity_text)
            assert chunk.text[idx : idx + len(entity_text)] == entity_text

    @requires_semantic_extract
    def test_entity_aware_chunker_with_pattern_ner(self):
        pytest.importorskip("semantica.semantic_extract")
        text = (
            "Alice Johnson founded Acme Corporation in New York. "
            "Bob Smith joined the company later. "
            "They expanded operations across Europe and Asia. "
        ) * 5
        chunker = EntityAwareChunker(
            chunk_size=120, ner_method="pattern", preserve_entities=True
        )
        chunks = chunker.chunk(text)
        assert len(chunks) >= 1
        assert all(isinstance(c, Chunk) for c in chunks)


# ---------------------------------------------------------------------------
# RelationAware / GraphBased / OntologyAware / Hierarchical
# ---------------------------------------------------------------------------


class TestRelationAwareChunker:
    def test_init(self):
        chunker = RelationAwareChunker(chunk_size=100, relation_method="pattern")
        assert chunker.chunk_size == 100
        assert chunker.relation_method == "pattern"

    @requires_semantic_extract
    def test_chunk_with_pattern_extractors(self):
        pytest.importorskip("semantica.semantic_extract")
        text = (
            "Alice works at Acme. Bob reports to Alice. "
            "Carol founded Acme in 2010. More padding text follows here. "
        ) * 4
        chunker = RelationAwareChunker(
            chunk_size=100, relation_method="pattern", ner_method="pattern"
        )
        chunks = chunker.chunk(text)
        assert isinstance(chunks, list)
        assert len(chunks) >= 1
        assert all(isinstance(c, Chunk) for c in chunks)


class TestGraphBasedChunker:
    def test_init(self):
        chunker = GraphBasedChunker(
            chunk_size=500, strategy="community", algorithm="louvain"
        )
        assert chunker.strategy == "community"
        assert chunker.algorithm == "louvain"

    @requires_semantic_extract
    @requires_networkx
    def test_chunk_with_real_optional_deps(self):
        pytest.importorskip("networkx")
        pytest.importorskip("semantica.semantic_extract")
        text = (
            "Alice met Bob at Acme Corporation yesterday afternoon. "
            "Bob introduced Carol to the Acme engineering team. "
            "Carol and Alice later discussed graph-based retrieval methods. "
        ) * 3
        chunker = GraphBasedChunker(
            chunk_size=200,
            strategy="community",
            algorithm="louvain",
            ner_method="pattern",
            relation_method="pattern",
        )
        chunks = chunker.chunk(text)
        assert len(chunks) >= 1
        assert all(isinstance(c, Chunk) for c in chunks)
        # Ensure the graph-based path actually ran (not fallback-to-recursive).
        assert any(
            c.metadata.get("method") == "graph_based" for c in chunks
        ), "Expected at least one graph_based chunk"
        assert any(
            c.metadata.get("strategy") == "community"
            and c.metadata.get("algorithm") == "louvain"
            for c in chunks
        ), "Expected graph_based chunk metadata to include strategy/algorithm"
        assert not any(
            c.metadata.get("method") == "recursive" for c in chunks
        ), "Graph-based fallback to recursive was triggered"


class TestOntologyAwareChunker:
    def test_init(self):
        chunker = OntologyAwareChunker(chunk_size=200, preserve_concepts=True)
        assert chunker.chunk_size == 200
        assert chunker.preserve_concepts is True

    @requires_semantic_extract
    def test_chunk_uses_entity_aware_path(self):
        pytest.importorskip("semantica.semantic_extract")
        text = "Concept Alpha relates to Concept Beta in the taxonomy. " * 8
        chunker = OntologyAwareChunker(
            chunk_size=120, preserve_concepts=True, ner_method="pattern"
        )
        chunks = chunker.chunk(text)
        assert len(chunks) >= 1
        assert all(isinstance(c, Chunk) for c in chunks)


class TestHierarchicalChunker:
    def test_hierarchical_markdown_sections(self):
        text = """# Section One

Paragraph under section one with enough content to matter.

# Section Two

Paragraph under section two also with sufficient content.
"""
        chunker = HierarchicalChunker(
            levels=["section", "paragraph"], chunk_sizes=[2000, 500]
        )
        chunks = chunker.chunk(text)
        assert len(chunks) >= 1
        for chunk in chunks:
            assert chunk.metadata.get("hierarchical") is True
            assert chunk.metadata.get("levels") == ["section", "paragraph"]

    def test_split_hierarchical_function(self):
        text = "Para one.\n\nPara two.\n\nPara three."
        chunks = split_hierarchical(text, levels=["paragraph"], chunk_sizes=[1000])
        assert len(chunks) >= 1


# ---------------------------------------------------------------------------
# Exported method functions (public API smoke coverage)
# ---------------------------------------------------------------------------


class TestSplitMethodFunctions:
    SAMPLE = (
        "First sentence about knowledge graphs. "
        "Second sentence covers entity extraction. "
        "Third sentence discusses relation awareness. "
        "Fourth sentence wraps up the example."
    )

    MARKDOWN = """# Intro

Intro paragraph with enough text to matter for structural splitting.

# Body

Body paragraph under a distinct heading for separation checks.
"""

    def test_split_recursive(self):
        chunks = split_recursive(self.SAMPLE, chunk_size=60)
        assert len(chunks) >= 1
        assert all(isinstance(c, Chunk) for c in chunks)

    def test_split_by_sentences(self):
        chunks = split_by_sentences(self.SAMPLE, chunk_size=80)
        assert len(chunks) >= 1

    def test_split_by_paragraphs(self):
        text = "Para A content here.\n\nPara B content here.\n\nPara C content here."
        chunks = split_by_paragraphs(text, chunk_size=50)
        assert len(chunks) >= 1

    def test_split_by_characters(self):
        chunks = split_by_characters(self.SAMPLE, chunk_size=40)
        assert len(chunks) >= 2

    def test_split_by_words(self):
        chunks = split_by_words(self.SAMPLE, chunk_size=10)
        assert len(chunks) >= 1

    def test_split_structural(self):
        chunks = split_structural(
            self.MARKDOWN, max_chunk_size=80, respect_headers=True
        )
        assert len(chunks) >= 2
        assert all(isinstance(c, Chunk) for c in chunks)

    def test_split_sliding_window(self):
        chunks = split_sliding_window(
            self.SAMPLE * 3,
            chunk_size=40,
            overlap=10,
            preserve_boundaries=False,
        )
        assert len(chunks) >= 2
        assert all(isinstance(c, Chunk) for c in chunks)
        # Verify the sliding-window path was taken, not the recursive fallback.
        # chunks[1].metadata["has_overlap"] is set only by SlidingWindowChunker.
        assert chunks[1].metadata.get("has_overlap") is True, (
            "Expected sliding-window chunks to carry has_overlap=True; "
            "fallback to recursive may have occurred"
        )
        assert chunks[1].metadata.get("method") != "recursive", (
            "Sliding-window fallback to recursive was triggered unexpectedly"
        )

    @requires_semantic_extract
    def test_split_entity_aware(self):
        pytest.importorskip("semantica.semantic_extract")
        chunks = split_entity_aware(
            self.SAMPLE * 3, chunk_size=80, ner_method="pattern"
        )
        assert len(chunks) >= 1

    @requires_semantic_extract
    def test_split_relation_aware(self):
        pytest.importorskip("semantica.semantic_extract")
        chunks = split_relation_aware(
            self.SAMPLE * 3,
            chunk_size=80,
            relation_method="pattern",
            ner_method="pattern",
        )
        assert len(chunks) >= 1

    @requires_semantic_extract
    @requires_networkx
    def test_split_graph_based(self):
        pytest.importorskip("networkx")
        pytest.importorskip("semantica.semantic_extract")
        chunks = split_graph_based(
            self.SAMPLE * 3,
            chunk_size=120,
            strategy="community",
            algorithm="louvain",
            ner_method="pattern",
            relation_method="pattern",
        )
        assert len(chunks) >= 1
        assert all(isinstance(c, Chunk) for c in chunks)
        # Ensure we didn't satisfy the test via the broad recursive fallback.
        assert any(
            c.metadata.get("method") == "graph_based" for c in chunks
        ), "Expected at least one graph_based chunk"
        assert any(
            c.metadata.get("strategy") == "community"
            and c.metadata.get("algorithm") == "louvain"
            for c in chunks
        ), "Expected graph_based chunk metadata to include strategy/algorithm"
        assert not any(
            c.metadata.get("method") == "recursive" for c in chunks
        ), "Graph-based fallback to recursive was triggered"

    @requires_semantic_extract
    def test_split_ontology_aware(self):
        pytest.importorskip("semantica.semantic_extract")
        chunks = split_ontology_aware(
            self.SAMPLE * 3, chunk_size=80, ner_method="pattern"
        )
        assert len(chunks) >= 1
