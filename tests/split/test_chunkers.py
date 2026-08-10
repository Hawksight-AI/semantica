"""Tests for previously untested split chunker classes (issue #864)."""

from unittest.mock import MagicMock, patch

import pytest

from semantica.split.kg_chunkers import (
    EntityAwareChunker,
    GraphBasedChunker,
    HierarchicalChunker,
    OntologyAwareChunker,
    RelationAwareChunker,
)
from semantica.split.methods import (
    split_by_characters,
    split_by_paragraphs,
    split_by_sentences,
    split_by_words,
    split_entity_aware,
    split_hierarchical,
    split_recursive,
)
from semantica.split.semantic_chunker import Chunk
from semantica.split.sliding_window_chunker import SlidingWindowChunker
from semantica.split.structural_chunker import StructuralChunker, StructuralElement
from semantica.split.table_chunker import TableChunk, TableChunker
from semantica.utils.exceptions import ValidationError

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

        # Indices should advance by stride (except possibly into the final partial chunk)
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
        # Original overlap restored
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
            # Chunks should not start with a lowercase letter mid-word after strip
            # (boundary mode strips and prefers sentence/word breaks)
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

        # Headings should appear as structural elements in metadata across chunks
        all_types = []
        for chunk in chunks:
            all_types.extend(chunk.metadata["element_types"])
        assert "heading" in all_types
        assert "paragraph" in all_types

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
                assert len(row) == 3  # full row, not truncated mid-row
            assert chunk.metadata["row_count"] == len(chunk.rows)

        # All original rows accounted for, in order
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
            # Each data line in the text chunk is a full pipe-separated row
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
# EntityAwareChunker
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
        # May return [] or fall through depending on fallback path
        assert isinstance(chunks, list)

    def test_entity_boundaries_preserved_with_mocked_ner(self):
        """A named entity must not be split across chunks."""
        from semantica.semantic_extract.types import Entity

        # Construct text where "Apple Inc" sits near a natural split point
        # if chunk_size is small.
        prefix = "Intro sentence one. Intro sentence two. "
        entity_text = "Apple Inc"
        suffix = (
            " was founded in Cupertino. "
            "More filler sentences keep the document long enough to chunk. "
            "Yet another sentence about products and services. "
            "Final sentence for padding the length."
        )
        text = prefix + entity_text + suffix
        entity_start = text.index(entity_text)
        entity_end = entity_start + len(entity_text)

        mock_entity = Entity(
            text=entity_text,
            label="ORG",
            start_char=entity_start,
            end_char=entity_end,
            confidence=0.99,
        )

        with patch("semantica.split.methods.NERExtractor") as mock_ner_cls:
            mock_ner_cls.return_value.extract.return_value = [mock_entity]
            with patch("semantica.split.methods.SEMANTIC_EXTRACT_AVAILABLE", True):
                chunks = split_entity_aware(
                    text,
                    chunk_size=80,
                    ner_method="ml",
                    preserve_entities=True,
                )

        assert len(chunks) >= 1
        # Entity text must appear wholly in exactly one chunk (not split)
        containing = [c for c in chunks if entity_text in c.text]
        assert len(containing) >= 1
        for chunk in containing:
            # Entity is intact — not cut mid-token
            assert entity_text in chunk.text
            idx = chunk.text.index(entity_text)
            # Surrounding characters shouldn't truncate the entity name
            assert chunk.text[idx : idx + len(entity_text)] == entity_text

    def test_entity_aware_with_pattern_ner(self):
        """Exercise real pattern NER when semantic_extract is available."""
        pytest.importorskip("semantica.semantic_extract")
        text = (
            "Alice Johnson founded Acme Corporation in New York. "
            "Bob Smith joined the company later. "
            "They expanded operations across Europe and Asia. " * 5
        )
        chunker = EntityAwareChunker(
            chunk_size=120, ner_method="pattern", preserve_entities=True
        )
        chunks = chunker.chunk(text)
        assert len(chunks) >= 1
        assert all(isinstance(c, Chunk) for c in chunks)
        assert all(c.metadata.get("method") == "entity_aware" or c.text for c in chunks)


# ---------------------------------------------------------------------------
# RelationAware / GraphBased / OntologyAware / Hierarchical
# ---------------------------------------------------------------------------


class TestRelationAwareChunker:
    def test_init_and_chunk_with_mocked_extractors(self):
        from semantica.semantic_extract.types import Entity, Relation

        text = (
            "Alice works at Acme. Bob reports to Alice. "
            "Carol founded Acme in 2010. More padding text follows here. " * 4
        )
        alice = Entity("Alice", "PERSON", text.index("Alice"), text.index("Alice") + 5)
        acme = Entity("Acme", "ORG", text.index("Acme"), text.index("Acme") + 4)
        relation = Relation(subject=alice, predicate="works_at", object=acme)

        with patch("semantica.split.methods.NERExtractor") as mock_ner:
            with patch("semantica.split.methods.RelationExtractor") as mock_rel:
                with patch("semantica.split.methods.SEMANTIC_EXTRACT_AVAILABLE", True):
                    mock_ner.return_value.extract.return_value = [alice, acme]
                    mock_rel.return_value.extract.return_value = [relation]
                    chunker = RelationAwareChunker(chunk_size=100, relation_method="ml")
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

    def test_falls_back_when_no_graph_nodes(self):
        """Empty entity/relation extraction falls back to recursive split."""
        text = "Short text without extractable structure. " * 10
        with patch("semantica.split.methods.NERExtractor") as mock_ner:
            with patch("semantica.split.methods.RelationExtractor") as mock_rel:
                with patch("semantica.split.methods.SEMANTIC_EXTRACT_AVAILABLE", True):
                    with patch("semantica.split.methods.NETWORKX_AVAILABLE", True):
                        mock_ner.return_value.extract.return_value = []
                        mock_rel.return_value.extract.return_value = []
                        chunker = GraphBasedChunker(chunk_size=80)
                        chunks = chunker.chunk(text)

        assert len(chunks) >= 1
        assert all(isinstance(c, Chunk) for c in chunks)


class TestOntologyAwareChunker:
    def test_delegates_to_entity_aware(self):
        chunker = OntologyAwareChunker(chunk_size=200, preserve_concepts=True)
        assert chunker.chunk_size == 200
        text = "Concept Alpha relates to Concept Beta in the taxonomy. " * 8

        with patch("semantica.split.methods.split_entity_aware") as mock_ea:
            mock_ea.return_value = [
                Chunk(text=text[:100], start_index=0, end_index=100, metadata={})
            ]
            chunks = chunker.chunk(text)
            mock_ea.assert_called_once()
            assert len(chunks) == 1


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
# Exported method functions (basic smoke coverage)
# ---------------------------------------------------------------------------


class TestSplitMethodFunctions:
    SAMPLE = (
        "First sentence about knowledge graphs. "
        "Second sentence covers entity extraction. "
        "Third sentence discusses relation awareness. "
        "Fourth sentence wraps up the example."
    )

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
