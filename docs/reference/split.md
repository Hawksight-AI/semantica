---
title: "Split Module"
description: "Text chunking with recursive, semantic, entity-aware, relation-aware, structural, and sliding window splitting."
icon: "scissors"
---

**`semantica.split`** breaks documents into chunks that **preserve semantic context**:

- Six chunking strategies: recursive, semantic, entity-aware, relation-aware, sliding window, structural
- `SemanticChunker` uses embedding-based topic-shift detection to split only when content changes
- `EntityAwareChunker` keeps entity mentions intact across chunk boundaries
- `RelationAwareChunker` keeps subject-predicate-object triplets within a single chunk
- Chunking quality directly determines downstream embedding accuracy and entity extraction quality


## Why Chunking Matters

Most LLMs and embedding models have fixed context windows. Documents larger than that window must be split. But naive splitting (every 500 characters, regardless of structure) destroys semantic context:

- An entity mention like "Apple Inc." split across two chunks loses its context in both
- A relation triplet like "Steve Jobs founded Apple" split at "Steve Jobs" leaves a dangling subject
- Embedding a chunk that mixes two unrelated topics produces a centroid vector that matches neither

Semantica's chunking methods are designed to avoid these failure modes.

## Exported Classes

| Class | Role |
| :--- | :--- |
| `TextSplitter` | Unified entry point — swap `method=` without changing downstream code |
| `Chunk` | `{text, start_index, end_index, metadata, id}` |
| `SemanticChunker` | Embedding-based topic-shift detection — splits only when content actually changes |
| `StructuralChunker` | Heading/section-based splits using structural text analysis |
| `EntityAwareChunker` | Prevents named entity mentions from being split across chunk boundaries |
| `RelationAwareChunker` | Keeps subject-predicate-object triplets intact within a single chunk |
| `HierarchicalChunker` | Multi-level chunking producing parent/child chunk relationships |

**Available `method=` values for `TextSplitter`:**

| Method | Best for |
| :--- | :--- |
| `recursive` | General text — splits on paragraphs, sentences, words in order |
| `sentence` | Conversational text, QA |
| `paragraph` | Long-form text where paragraph integrity matters |
| `token` | LLM context window enforcement |
| `semantic_transformer` | Long documents with topic shifts |
| `entity_aware` | KG extraction pipelines |
| `relation_aware` | KG pipelines where triplet integrity matters |
| `structural` | Text with heading/paragraph structure |
| `sliding_window` | Dense overlap for bi-encoder retrieval |

## What You Get

<CardGroup cols={2}>
  <Card title="TextSplitter" icon="scissors">
    Unified interface for 11 chunking strategies — swap methods without changing downstream code.
  </Card>
  <Card title="Semantic Chunking" icon="brain">
    Embedding-based topic shift detection — splits only when the topic actually changes.
  </Card>
  <Card title="Entity-Aware Chunking" icon="user">
    Entity spans never cross chunk boundaries — guaranteed by boundary adjustment.
  </Card>
  <Card title="Relation-Aware Chunking" icon="arrows-left-right">
    Subject–predicate–object triplets kept within a single chunk for KG pipelines.
  </Card>
  <Card title="Chunk Object" icon="box">
    Output dataclass with text, character offsets, optional id, and method-specific metadata.
  </Card>
</CardGroup>

## Quick Start

<Steps>
  <Step title="Choose a splitting method">
    ```python
    from semantica.split import TextSplitter

    splitter = TextSplitter(
        method="recursive",   # see Splitting Methods table
        chunk_size=1000,
        chunk_overlap=200,
    )
    ```
  </Step>
  <Step title="Split raw text">
    ```python
    chunks = splitter.split(text)

    for chunk in chunks:
        print(f"  Start: {chunk.start_index}, End: {chunk.end_index}")
        print(f"  Method: {chunk.metadata.get('method')}")
        print(f"  Preview: {chunk.text[:80]}...")
    ```
  </Step>
  <Step title="Or split a document object">
    ```python
    # split_documents() accepts any object with a .text attribute,
    # or a plain string — no specific document class required.
    class Doc:
        def __init__(self, text, metadata=None):
            self.text = text
            self.metadata = metadata or {}

    doc = Doc(text="Annual report content...", metadata={"source": "annual_report.pdf"})

    splitter = TextSplitter(method="structural")
    chunks   = splitter.split_documents([doc])

    for chunk in chunks:
        print(f"  {chunk.text[:80]}...")
    ```
  </Step>
  <Step title="Batch-split a list of documents">
    ```python
    # split_documents() returns a flat List[Chunk] across all inputs
    all_chunks = splitter.split_documents(docs)

    for chunk in all_chunks:
        print(chunk.text[:80])
    ```
  </Step>
</Steps>

## Splitting Methods

| Method | How It Splits | Best For |
| :------ | :------------- | :-------- |
| `recursive` | Paragraph → sentence → word (cascading fallback) | General-purpose default |
| `semantic_transformer` | Embeds sentences, splits at cosine similarity drops | RAG — topic coherence matters |
| `entity_aware` | Adjusts boundaries so entity spans are never cut | NER pipelines |
| `relation_aware` | Keeps subject–predicate–object triplets within one chunk | KG construction |
| `sentence` | Sentence boundary detection (regex, NLTK, spaCy) | Short documents, Q&A |
| `paragraph` | Paragraph boundary splitting | Long-form articles, reports |
| `token` | Token count via tiktoken or transformers; hard cutoff | LLM context window prep |
| `word` | Word count with overlap | Simple token-approximate splits |
| `character` | Fixed character count with overlap; fastest, no NLP | Simple batch jobs |
| `sliding_window` | Fixed-size window advancing by stride; configurable overlap | Dense retrieval (ColBERT, DPR) |
| `structural` | Heading/paragraph structure detection | Text with explicit heading hierarchy |
| `embedding_semantic` | Embedding similarity boundaries (alias of `semantic_transformer`) | RAG with embedding-based coherence |
| `hierarchical` | Multi-level section → paragraph → sentence chunking | Multi-granularity retrieval |

## Choosing a Strategy

Use this decision tree before picking a method:

- **Building a KG?** → `relation_aware` (keeps triplets intact), then `entity_aware` for pure NER
- **RAG system where retrieval quality matters most?** → `semantic_transformer`
- **Dense overlap for bi-encoder retrieval (ColBERT, DPR)?** → `sliding_window`
- **Preparing prompts for a fixed-window LLM?** → `token`
- **Structured text with headings?** → `structural`
- **Paragraph-level coherence?** → `paragraph` or `sentence`
- **Fast splitting with no NLP overhead?** → `recursive` or `character`

## TextSplitter Constructor

```python
from semantica.split import TextSplitter

splitter = TextSplitter(
    method="semantic_transformer",   # chunking strategy — see Splitting Methods table
    chunk_size=1000,                 # target size in characters
    chunk_overlap=200,               # character overlap between adjacent chunks
    similarity_threshold=0.7,        # cosine similarity cutoff (semantic_transformer only)
    model="all-MiniLM-L6-v2",        # sentence-transformers model name (semantic_transformer only)
    ner_method="ml",                 # NER method (entity_aware only)
    relation_method="ml",            # relation extraction method (relation_aware only)
)
```

| Parameter | Type | Default | Description |
| :--------- | :---- | :------- | :----------- |
| `method` | `str \| list[str]` | `"recursive"` | Chunking strategy, or list of methods as fallback chain |
| `chunk_size` | `int` | `1000` | Target size in **characters** (not tokens — if you were using token-based sizing before, multiply by ~4 to approximate the same boundary) |
| `chunk_overlap` | `int` | `200` | Character overlap between adjacent chunks |
| `similarity_threshold` | `float` | `0.7` | Cosine similarity cutoff for `semantic_transformer` — lower = more splits |
| `model` | `str` | `"all-MiniLM-L6-v2"` | Sentence-transformers model name for `semantic_transformer` |
| `ner_method` | `str` | `"ml"` | NER method for `entity_aware`: `"pattern"` \| `"regex"` \| `"ml"` \| `"huggingface"` \| `"llm"` |
| `relation_method` | `str` | `"ml"` | Relation extraction method for `relation_aware`: `"ml"` \| `"llm"` \| `"huggingface"` |
| `tokenizer` | `str` | `"gpt-4"` | tiktoken model name for `token` method — unrecognised names fall back to `cl100k_base` |

## Splitting Method Details

<Tabs>
  <Tab title="Recursive (default)">
    Tries paragraph breaks first, then sentence boundaries, then word boundaries — falling back only when the chunk exceeds `chunk_size`:

    ```python
    splitter = TextSplitter(method="recursive", chunk_size=1000, chunk_overlap=200)
    chunks   = splitter.split(text)
    ```

    **Key behaviours:**
    - Preserves paragraph and sentence structure wherever possible
    - Falls back gracefully — never produces chunks larger than `chunk_size`
    - Overlap ensures context continuity across chunk boundaries
    - Good starting point when you're unsure which method to use
  </Tab>
  <Tab title="Semantic">
    Embeds each sentence using a sentence-transformers model, then splits whenever cosine similarity between consecutive sentences drops below `similarity_threshold`. Each chunk covers one coherent topic:

    ```python
    from semantica.split import TextSplitter

    splitter = TextSplitter(
        method="semantic_transformer",
        model="all-MiniLM-L6-v2",      # any sentence-transformers model name
        similarity_threshold=0.7,       # 0.6 = more splits, 0.8 = fewer splits
        chunk_size=800,
        chunk_overlap=0,                # not needed — chunks are already coherent
    )
    chunks = splitter.split(text)
    ```

    **Key behaviours:**
    - Requires the `sentence-transformers` package — uses `all-MiniLM-L6-v2` by default, configurable via `model=`
    - Produces variable-length chunks — some topics are short, others long
    - Falls back to sentence splitting if `sentence-transformers` is not installed
    - Slower than `recursive` due to embedding computation; cache embeddings for repeated splits
  </Tab>
  <Tab title="Entity-Aware">
    Runs NER internally, then adjusts chunk boundaries so no entity mention is split across two chunks:

    ```python
    from semantica.split import TextSplitter
    import os

    # ner_method is passed through to the internal NERExtractor.
    # Use "llm" for highest accuracy, "ml" (default) for speed.
    splitter = TextSplitter(
        method="entity_aware",
        chunk_size=512,
        chunk_overlap=50,
        ner_method="ml",   # "pattern" | "regex" | "ml" | "huggingface" | "llm"
    )
    chunks = splitter.split(text)

    for chunk in chunks:
        print(f"  entities in chunk: {chunk.metadata.get('entity_count', 0)}")
        print(f"  preview: {chunk.text[:80]}...")
    ```

    **Key behaviours:**
    - NER is run internally — entity extraction happens automatically inside the splitter
    - Entity objects are available in `chunk.metadata["entities"]` for each chunk
    - Chunk sizes vary slightly from `chunk_size` — boundary adjustments are ≤ one sentence
    - Works with all entity types: PERSON, ORGANIZATION, LOCATION, DATE, custom types
  </Tab>
  <Tab title="Relation-Aware">
    Keeps subject–predicate–object triplets within the same chunk — critical for KG pipelines:

    ```python
    from semantica.split import TextSplitter

    # relation_method is passed through to the internal RelationExtractor.
    # Use "llm" for highest accuracy, "ml" (default) for speed.
    splitter = TextSplitter(
        method="relation_aware",
        chunk_size=512,
        relation_method="ml",   # "ml" | "llm" | "huggingface"
    )
    chunks = splitter.split(text)

    for chunk in chunks:
        print(f"  relations in chunk: {chunk.metadata.get('relation_count', 0)}")
        for rel in chunk.metadata.get("relationships", []):
            print(f"  {rel}")
    ```

    **Key behaviours:**
    - Relation extraction is run internally — no pre-computed entities or triplets needed
    - Relation objects are available in `chunk.metadata["relationships"]` for each chunk
    - Implies entity-aware behaviour — both entities in a triplet are kept whole too
    - Best used as the split step in a `Parse → Split → Extract → Build KG` pipeline
  </Tab>
  <Tab title="Structural">
    Splits text based on structural analysis of headings and paragraph boundaries. Each heading or paragraph group becomes a chunk boundary:

    ```python
    from semantica.split import TextSplitter

    splitter = TextSplitter(method="structural")
    chunks   = splitter.split(text)

    for chunk in chunks:
        print(f"  {chunk.text[:80]}...")
        print(f"  start: {chunk.start_index}, end: {chunk.end_index}")
    ```

    **Key behaviours:**
    - Operates on plain text — no structural document format required
    - Respects heading hierarchy (lines starting with `#` or all-caps headings) and paragraph breaks  
    - Uses `max_chunk_size=` parameter instead of the standard `chunk_size=` for maximum size control
    - Falls back to `recursive` if `StructuralChunker` is unavailable
  </Tab>
</Tabs>

## Chunk Schema

<AccordionGroup>
  <Accordion title="Chunk dataclass">

```python
@dataclass
class Chunk:
    text:        str                    # the chunk's text content
    start_index: int                    # character offset of start in source text
    end_index:   int                    # character offset of end in source text
    metadata:    Dict[str, Any]         # method-specific fields — see table below
    id:          Optional[str] = None   # optional chunk identifier
```

  </Accordion>
  <Accordion title="Chunk metadata fields">

Metadata keys vary by method. Only keys that are actually set by the implementation are listed.

| Field | Type | Set by | Description |
| :----- | :---- | :------ | :----------- |
| `method` | `str` | all methods | Splitting method that produced this chunk |
| `chunk_size` | `int` | most methods | Character length of this chunk |
| `sentence_count` | `int` | `sentence`, `semantic_transformer`, spaCy path | Number of sentences in this chunk |
| `paragraph_count` | `int` | `paragraph` | Number of paragraphs in this chunk |
| `word_count` | `int` | `word` | Number of words in this chunk |
| `token_count` | `int` | `token`; `sentence`/`semantic_transformer` when spaCy is available | Token count — not always present |
| `entity_count` | `int` | `entity_aware` | Number of entities whose boundaries fall in this chunk |
| `entities` | `list` | `entity_aware` | Entity objects whose boundaries fall in this chunk |
| `relation_count` | `int` | `relation_aware` | Number of relation triplets in this chunk |
| `relationships` | `list` | `relation_aware` | Relation objects in this chunk |
| `element_count` | `int` | `structural` | Number of structural elements grouped into this chunk |
| `element_types` | `list[str]` | `structural` | Types of elements: `"heading"`, `"paragraph"`, `"list"`, etc. |

  </Accordion>
</AccordionGroup>

## Tokenizer Options

The `token` method accepts a `tokenizer=` kwarg that is passed to `tiktoken.encoding_for_model()`. The value should be a tiktoken model name. Unrecognised names fall back to `cl100k_base` automatically.

| Value | Encoding used |
| :----- | :------------- |
| `"gpt-4"` (default) | `cl100k_base` |
| `"gpt-3.5-turbo"` | `cl100k_base` |
| `"text-embedding-ada-002"` | `cl100k_base` |
| Any unrecognised string | Falls back to `cl100k_base` |

If `tiktoken` is not installed, the `token` method falls back to splitting by whitespace-separated words.

## Pipeline Integration

`TextSplitter` can be used standalone or composed manually with other Semantica modules. The example below shows a sequential pattern — parse a file, split the text, then extract entities from each chunk:

```python
from semantica.parse import DocumentParser
from semantica.split import TextSplitter
from semantica.semantic_extract import NERExtractor

# Parse
parser = DocumentParser()
parsed = parser.parse("data/report.pdf")   # returns a dict with "full_text" key

# Split
splitter = TextSplitter(method="semantic_transformer", chunk_size=512)
chunks   = splitter.split(parsed["full_text"])

# Extract from each chunk
ner = NERExtractor(method="ml")

for chunk in chunks:
    entities = ner.extract(chunk.text)
    print(f"  {len(entities)} entities in chunk starting at {chunk.start_index}")
```

For the full pipeline orchestration API, see the [Pipeline reference](pipeline).

## Tips and Common Pitfalls

<Warning>
  **`chunk_overlap` too small.** Without overlap, a fact that spans a chunk boundary is invisible in both chunks. A 10–20% overlap relative to `chunk_size` is a safe minimum — for `chunk_size=1000`, set `chunk_overlap=100` to `200`.
</Warning>

<Warning>
  **Wrong tokenizer.** The `token` method passes the `tokenizer=` value to `tiktoken.encoding_for_model()`. If the model name is not recognised by tiktoken it silently falls back to `cl100k_base`. Pass a valid tiktoken model name (e.g. `"gpt-4"`, `"gpt-3.5-turbo"`) to get deterministic behaviour.
</Warning>

<Tip>
  **Semantic splitting needs enough sentences.** `semantic_transformer` needs several sentences to detect topic shifts. On documents shorter than ~300 words it behaves like `sentence` splitting — use `recursive` instead.
</Tip>

<CardGroup cols={2}>
  <Card title="Parse" icon="file-lines" href="parse">
    Parse documents before chunking — produces sections and metadata.
  </Card>
  <Card title="Embeddings" icon="vector-square" href="embeddings">
    Embed chunks for vector search and semantic chunking.
  </Card>
  <Card title="Semantic Extract" icon="magnifying-glass" href="semantic_extract">
    Extract entities and relations from individual chunks.
  </Card>
  <Card title="Pipeline" icon="gear" href="pipeline">
    Integrate splitting as a named pipeline step.
  </Card>
</CardGroup>
