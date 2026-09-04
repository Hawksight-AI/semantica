"""
Input schema definitions for all MCP tools.

Each entry is the JSON Schema object placed in the tool's ``inputSchema``
field.  Keeping them here avoids duplication across tool modules.
"""

EXTRACTION_TEXT = {
    "type": "object",
    "properties": {
        "text": {
            "type": "string",
            "description": "Input text to process",
        }
    },
    "required": ["text"],
}

EXTRACT_ENTITIES = EXTRACTION_TEXT

EXTRACT_RELATIONS = EXTRACTION_TEXT

EXTRACT_ALL = {
    "type": "object",
    "properties": {
        "text": {"type": "string", "description": "Input text to process"},
        "include_events": {
            "type": "boolean",
            "description": "Also extract events (default: true)",
        },
        "include_triplets": {
            "type": "boolean",
            "description": "Also extract (subject, predicate, object) triplets (default: true)",
        },
    },
    "required": ["text"],
}

RECORD_DECISION = {
    "type": "object",
    "properties": {
        "category": {
            "type": "string",
            "description": "Decision category, e.g. 'loan_approval', 'deployment'",
        },
        "scenario": {
            "type": "string",
            "description": "Natural-language description of the situation",
        },
        "reasoning": {
            "type": "string",
            "description": "Explanation of why this decision was made",
        },
        "outcome": {
            "type": "string",
            "description": "Decision result, e.g. 'approved', 'rejected', 'deferred'",
        },
        "confidence": {
            "type": "number",
            "minimum": 0,
            "maximum": 1,
            "description": "Confidence score between 0 and 1",
        },
        "decision_maker": {
            "type": "string",
            "description": "Who or what made the decision (default: mcp_client)",
        },
        "valid_from": {
            "type": "string",
            "description": "ISO 8601 validity start date (optional)",
        },
        "valid_until": {
            "type": "string",
            "description": "ISO 8601 validity end date (optional)",
        },
    },
    "required": ["category", "scenario", "reasoning", "outcome", "confidence"],
}

QUERY_DECISIONS = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "description": "Natural language query (optional)",
        },
        "category": {
            "type": "string",
            "description": "Filter by exact category (optional)",
        },
        "outcome": {
            "type": "string",
            "description": "Filter by outcome value (optional)",
        },
        "limit": {
            "type": "integer",
            "minimum": 1,
            "maximum": 200,
            "description": "Maximum number of results (default: 10)",
        },
    },
}

FIND_PRECEDENTS = {
    "type": "object",
    "properties": {
        "scenario": {
            "type": "string",
            "description": "Scenario description to find similar past decisions for",
        },
        "max_results": {
            "type": "integer",
            "minimum": 1,
            "maximum": 50,
            "description": "Maximum number of precedents to return (default: 5)",
        },
    },
    "required": ["scenario"],
}

GET_CAUSAL_CHAIN = {
    "type": "object",
    "properties": {
        "decision_id": {
            "type": "string",
            "description": "ID of the decision to trace",
        },
        "direction": {
            "type": "string",
            "enum": ["upstream", "downstream", "both"],
            "description": "Trace direction (default: downstream)",
        },
        "max_depth": {
            "type": "integer",
            "minimum": 1,
            "maximum": 20,
            "description": "Maximum chain depth (default: 5)",
        },
    },
    "required": ["decision_id"],
}

ANALYZE_DECISION_IMPACT = {
    "type": "object",
    "properties": {
        "decision_id": {
            "type": "string",
            "description": "ID of the decision to analyse",
        },
    },
    "required": ["decision_id"],
}

ADD_ENTITY = {
    "type": "object",
    "properties": {
        "id": {
            "type": "string",
            "description": "Unique node identifier",
        },
        "label": {
            "type": "string",
            "description": "Human-readable label (defaults to id)",
        },
        "type": {
            "type": "string",
            "description": "Node type, e.g. 'Person', 'Organisation', 'Concept'",
        },
        "metadata": {
            "type": "object",
            "description": "Additional key-value properties",
        },
    },
    "required": ["id"],
}

ADD_RELATIONSHIP = {
    "type": "object",
    "properties": {
        "source": {
            "type": "string",
            "description": "Source node ID",
        },
        "target": {
            "type": "string",
            "description": "Target node ID",
        },
        "type": {
            "type": "string",
            "description": "Relationship type, e.g. 'WORKS_AT', 'CAUSED_BY'",
        },
        "metadata": {
            "type": "object",
            "description": "Additional edge properties",
        },
    },
    "required": ["source", "target"],
}

SEARCH_GRAPH = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "description": "Search term or phrase",
        },
        "node_type": {
            "type": "string",
            "description": "Filter by node type (optional)",
        },
        "limit": {
            "type": "integer",
            "description": "Max results (default: 20)",
        },
    },
    "required": ["query"],
}

RUN_REASONING = {
    "type": "object",
    "properties": {
        "facts": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Fact strings, e.g. ['Person(John)', 'Employee(John)']",
        },
        "rules": {
            "type": "array",
            "items": {"type": "string"},
            "description": "IF/THEN rule strings, e.g. ['IF Employee(?x) THEN Worker(?x)']",
        },
    },
    "required": ["facts", "rules"],
}

ABDUCTIVE_REASONING = {
    "type": "object",
    "properties": {
        "observations": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Observed facts to explain",
        },
        "max_hypotheses": {
            "type": "integer",
            "description": "Max hypotheses to generate (default: 5)",
        },
    },
    "required": ["observations"],
}

EXPORT_GRAPH = {
    "type": "object",
    "properties": {
        "format": {
            "type": "string",
            "enum": ["turtle", "ttl", "nt", "xml", "json-ld", "json", "csv"],
            "description": "Export format (default: json-ld)",
        },
    },
}

GET_PROVENANCE = {
    "type": "object",
    "properties": {
        "entity_id": {
            "type": "string",
            "description": "Entity or node ID to get provenance for",
        },
    },
    "required": ["entity_id"],
}

GET_ANALYTICS = {
    "type": "object",
    "properties": {
        "metrics": {
            "type": "array",
            "items": {
                "type": "string",
                "enum": ["pagerank", "betweenness", "communities", "degree", "all"],
            },
            "description": "Analytics to compute (default: ['all'])",
        },
        "top_n": {
            "type": "integer",
            "description": "Top N nodes to return per metric (default: 10)",
        },
    },
}

STORE_DOCUMENT = {
    "type": "object",
    "properties": {
        "content": {
            "type": "string",
            "description": "Document text to chunk and store for semantic retrieval",
        },
        "source": {
            "type": "string",
            "description": "Provenance identifier, e.g. 'policy_manual_v2#page12'",
        },
        "authority": {
            "type": "string",
            "description": "Authority level of the content, e.g. 'official', 'draft', 'external'",
        },
        "version": {
            "type": "string",
            "description": "Document version tag used together with source as the upsert key (default: 'v1')",
        },
        "project": {
            "type": "string",
            "description": "Optional project namespace for later filtering",
        },
        "metadata": {
            "type": "object",
            "description": "Additional key-value properties stored on every chunk",
        },
        "chunk_size": {
            "type": "integer",
            "minimum": 100,
            "description": "Chunk window in characters (default: 1000)",
        },
        "chunk_overlap": {
            "type": "integer",
            "minimum": 0,
            "description": "Overlap between consecutive chunks in characters (default: 200)",
        },
    },
    "required": ["content", "source", "authority"],
}

RETRIEVE_CONTEXT = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "description": "Natural language query to embed and search for",
        },
        "top_k": {
            "type": "integer",
            "minimum": 1,
            "maximum": 10,
            "description": "Maximum number of chunks to return (default: 5, capped at 10)",
        },
        "project": {
            "type": "string",
            "description": "Only return chunks stored under this project namespace (optional)",
        },
    },
    "required": ["query"],
}

UPDATE_DOCUMENT = {
    "type": "object",
    "properties": {
        "content": {
            "type": "string",
            "description": "New document text replacing the stored version",
        },
        "source": {
            "type": "string",
            "description": "Provenance identifier of the document to update",
        },
        "version": {
            "type": "string",
            "description": "Version tag identifying which stored version to replace (default: 'v1')",
        },
        "authority": {
            "type": "string",
            "description": "Updated authority level (defaults to the stored value)",
        },
        "project": {
            "type": "string",
            "description": "Updated project namespace (defaults to the stored value)",
        },
        "metadata": {
            "type": "object",
            "description": "Additional key-value properties merged into chunk metadata",
        },
        "chunk_size": {
            "type": "integer",
            "minimum": 100,
            "description": "Chunk window in characters (default: 1000)",
        },
        "chunk_overlap": {
            "type": "integer",
            "minimum": 0,
            "description": "Overlap between consecutive chunks in characters (default: 200)",
        },
    },
    "required": ["content", "source"],
}

REMOVE_DOCUMENT = {
    "type": "object",
    "properties": {
        "source": {
            "type": "string",
            "description": "Provenance identifier of the document to remove",
        },
        "version": {
            "type": "string",
            "description": "Version tag identifying which stored version to remove (default: 'v1')",
        },
    },
    "required": ["source"],
}

EMPTY = {"type": "object", "properties": {}}
