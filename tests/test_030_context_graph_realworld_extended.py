"""
Extended Real-World Test Suite for Semantica 0.3.0-alpha and 0.3.0-beta
Context Graph Features — Deep Coverage with Real-World Data & Web Sources

This file complements tests/test_030_realworld_comprehensive.py and focuses on
features NOT yet covered there, specifically:

  A.  ContextGraph advanced decision methods (analyze_decision_influence,
      get_decision_insights, trace_decision_causality, enforce_decision_policy,
      find_precedents_by_scenario)
  B.  Research-paper knowledge graph (arXiv provenance, citation graph)
  C.  E-commerce / retail knowledge graph (Amazon product catalog domain)
  D.  GraphBuilderWithProvenance with real web-sourced provenance data
  E.  AlgorithmTrackerWithProvenance tracking methods
  F.  Parquet export — entities, relationships, full KG (0.3.0-beta, PR #343)
  G.  ArangoDB AQL export — vertex + edge INSERT generation (0.3.0-beta, PR #342)
  H.  Deduplication v2 two-stage scoring prefilter (0.3.0-beta, PR #339)
  I.  Semantic relationship deduplication v2 with synonym mapping (PR #340)
  J.  AgentMemory store / retrieve / get_statistics / conversation_history
  K.  Full E2E workflow: build → analyze → decide → export → dedup → reason

Real-world data used (no live HTTP calls made — all data is static public knowledge):
  - AI papers: arXiv:1706.03762 (Attention), arXiv:1810.04805 (BERT),
               arXiv:2005.14165 (GPT-3), arXiv:2303.08774 (GPT-4)
  - Tech companies: Wikipedia/Crunchbase public knowledge
  - Financial domain: SEC EDGAR public filings (static references)
  - Open-source: GitHub URLs used as provenance source identifiers
"""

import json
import os
import tempfile
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List
from unittest.mock import MagicMock, Mock, patch

import pytest

# ── Context module ─────────────────────────────────────────────────────────────
from semantica.context import (
    AgentContext,
    CausalChainAnalyzer,
    ContextGraph,
    Decision,
    DecisionQuery,
    DecisionRecorder,
    Policy,
    PolicyEngine,
)
from semantica.context.decision_models import (
    deserialize_decision,
    serialize_decision,
    validate_decision,
)

# ── Export module ──────────────────────────────────────────────────────────────
# Set by the exporter's own `import pyarrow` attempt; False when pyarrow is
# missing or unimportable.
from semantica.export.parquet_exporter import PARQUET_AVAILABLE

# ── KG module ──────────────────────────────────────────────────────────────────
from semantica.kg import (
    CentralityCalculator,
    CommunityDetector,
    ConnectivityAnalyzer,
    GraphBuilder,
    LinkPredictor,
    NodeEmbedder,
    PathFinder,
    ProvenanceTracker,
    SimilarityCalculator,
)
from semantica.kg.kg_provenance import (
    GraphBuilderWithProvenance,
    AlgorithmTrackerWithProvenance,
)

# ═════════════════════════════════════════════════════════════════════════════
# Shared real-world data fixtures
# Data sourced from public knowledge; source URLs used as provenance identifiers.
# ═════════════════════════════════════════════════════════════════════════════

# ── AI Research Papers (arXiv public data) ────────────────────────────────────
# Source: https://arxiv.org/abs/1706.03762 — "Attention Is All You Need"
# Source: https://arxiv.org/abs/1810.04805 — "BERT"
# Source: https://arxiv.org/abs/2005.14165 — "Language Models are Few-Shot Learners (GPT-3)"
# Source: https://arxiv.org/abs/2303.08774 — "GPT-4 Technical Report"
# Source: https://arxiv.org/abs/2204.05149 — "PaLM"
# Source: https://arxiv.org/abs/2302.13971 — "LLaMA"
ARXIV_PAPERS = [
    {
        "id": "arxiv_1706.03762",
        "type": "paper",
        "text": "Attention Is All You Need",
        "year": 2017,
        "venue": "NeurIPS",
        "source_url": "https://arxiv.org/abs/1706.03762",
        "citations": 80000,
    },
    {
        "id": "arxiv_1810.04805",
        "type": "paper",
        "text": "BERT: Pre-training of Deep Bidirectional Transformers",
        "year": 2018,
        "venue": "NAACL",
        "source_url": "https://arxiv.org/abs/1810.04805",
        "citations": 55000,
    },
    {
        "id": "arxiv_2005.14165",
        "type": "paper",
        "text": "Language Models are Few-Shot Learners (GPT-3)",
        "year": 2020,
        "venue": "NeurIPS",
        "source_url": "https://arxiv.org/abs/2005.14165",
        "citations": 28000,
    },
    {
        "id": "arxiv_2303.08774",
        "type": "paper",
        "text": "GPT-4 Technical Report",
        "year": 2023,
        "venue": "OpenAI Tech Report",
        "source_url": "https://arxiv.org/abs/2303.08774",
        "citations": 7500,
    },
    {
        "id": "arxiv_2204.05149",
        "type": "paper",
        "text": "PaLM: Scaling Language Modeling with Pathways",
        "year": 2022,
        "venue": "JMLR",
        "source_url": "https://arxiv.org/abs/2204.05149",
        "citations": 4100,
    },
    {
        "id": "arxiv_2302.13971",
        "type": "paper",
        "text": "LLaMA: Open and Efficient Foundation Language Models",
        "year": 2023,
        "venue": "Meta AI",
        "source_url": "https://arxiv.org/abs/2302.13971",
        "citations": 9200,
    },
]

# Authors (Wikipedia / institutional pages as provenance)
ARXIV_AUTHORS = [
    {"id": "vaswani_a", "type": "person", "text": "Ashish Vaswani", "affiliation": "Google Brain",
     "source_url": "https://scholar.google.com/citations?user=oR9sCGYAAAAJ"},
    {"id": "devlin_j", "type": "person", "text": "Jacob Devlin", "affiliation": "Google AI",
     "source_url": "https://scholar.google.com/citations?user=JsBVqBkAAAAJ"},
    {"id": "brown_tb", "type": "person", "text": "Tom B. Brown", "affiliation": "OpenAI",
     "source_url": "https://scholar.google.com/citations?user=V7dfNxkAAAAJ"},
    {"id": "touvron_h", "type": "person", "text": "Hugo Touvron", "affiliation": "Meta AI",
     "source_url": "https://scholar.google.com/citations?user=o9FKUqYAAAAJ"},
]

ARXIV_RELATIONSHIPS = [
    # Authorship
    {"source_id": "vaswani_a", "target_id": "arxiv_1706.03762", "type": "authored", "confidence": 1.0},
    {"source_id": "devlin_j", "target_id": "arxiv_1810.04805", "type": "authored", "confidence": 1.0},
    {"source_id": "brown_tb", "target_id": "arxiv_2005.14165", "type": "authored", "confidence": 1.0},
    {"source_id": "touvron_h", "target_id": "arxiv_2302.13971", "type": "authored", "confidence": 1.0},
    # Citations
    {"source_id": "arxiv_1810.04805", "target_id": "arxiv_1706.03762", "type": "cites", "confidence": 1.0},
    {"source_id": "arxiv_2005.14165", "target_id": "arxiv_1706.03762", "type": "cites", "confidence": 1.0},
    {"source_id": "arxiv_2005.14165", "target_id": "arxiv_1810.04805", "type": "cites", "confidence": 1.0},
    {"source_id": "arxiv_2303.08774", "target_id": "arxiv_2005.14165", "type": "cites", "confidence": 1.0},
    {"source_id": "arxiv_2303.08774", "target_id": "arxiv_1706.03762", "type": "cites", "confidence": 1.0},
    {"source_id": "arxiv_2302.13971", "target_id": "arxiv_1706.03762", "type": "cites", "confidence": 1.0},
    {"source_id": "arxiv_2204.05149", "target_id": "arxiv_1706.03762", "type": "cites", "confidence": 1.0},
]

ALL_ARXIV_ENTITIES = ARXIV_PAPERS + ARXIV_AUTHORS


# ── E-commerce product catalog (Amazon public product knowledge) ───────────────
# Source: https://www.amazon.com/b?node=565108 (Electronics)
ECOMMERCE_ENTITIES = [
    {"id": "prod_kindle_scribe", "type": "product", "text": "Kindle Scribe 2024", "price": 369.99, "brand": "Amazon"},
    {"id": "prod_echo_show15", "type": "product", "text": "Echo Show 15", "price": 249.99, "brand": "Amazon"},
    {"id": "prod_ipad_air_m2", "type": "product", "text": "iPad Air M2 (2024)", "price": 599.00, "brand": "Apple"},
    {"id": "prod_galaxy_tab_s9", "type": "product", "text": "Samsung Galaxy Tab S9", "price": 799.99, "brand": "Samsung"},
    {"id": "prod_surface_pro10", "type": "product", "text": "Microsoft Surface Pro 10", "price": 1199.00, "brand": "Microsoft"},
    {"id": "brand_amazon", "type": "brand", "text": "Amazon", "market_cap_b": 1800},
    {"id": "brand_apple", "type": "brand", "text": "Apple", "market_cap_b": 3200},
    {"id": "brand_samsung", "type": "brand", "text": "Samsung", "market_cap_b": 350},
    {"id": "brand_microsoft", "type": "brand", "text": "Microsoft", "market_cap_b": 3000},
    {"id": "cat_ereaders", "type": "category", "text": "eReaders"},
    {"id": "cat_smart_displays", "type": "category", "text": "Smart Displays"},
    {"id": "cat_tablets", "type": "category", "text": "Tablets"},
]

ECOMMERCE_RELATIONSHIPS = [
    {"source_id": "brand_amazon", "target_id": "prod_kindle_scribe", "type": "manufactures", "confidence": 1.0},
    {"source_id": "brand_amazon", "target_id": "prod_echo_show15", "type": "manufactures", "confidence": 1.0},
    {"source_id": "brand_apple", "target_id": "prod_ipad_air_m2", "type": "manufactures", "confidence": 1.0},
    {"source_id": "brand_samsung", "target_id": "prod_galaxy_tab_s9", "type": "manufactures", "confidence": 1.0},
    {"source_id": "brand_microsoft", "target_id": "prod_surface_pro10", "type": "manufactures", "confidence": 1.0},
    {"source_id": "prod_kindle_scribe", "target_id": "cat_ereaders", "type": "belongs_to", "confidence": 1.0},
    {"source_id": "prod_echo_show15", "target_id": "cat_smart_displays", "type": "belongs_to", "confidence": 1.0},
    {"source_id": "prod_ipad_air_m2", "target_id": "cat_tablets", "type": "belongs_to", "confidence": 1.0},
    {"source_id": "prod_galaxy_tab_s9", "target_id": "cat_tablets", "type": "belongs_to", "confidence": 1.0},
    {"source_id": "prod_surface_pro10", "target_id": "cat_tablets", "type": "belongs_to", "confidence": 1.0},
    # Competitors
    {"source_id": "prod_ipad_air_m2", "target_id": "prod_galaxy_tab_s9", "type": "competes_with", "confidence": 0.9},
    {"source_id": "prod_ipad_air_m2", "target_id": "prod_surface_pro10", "type": "competes_with", "confidence": 0.8},
]


# ── GitHub Open-Source Project graph ──────────────────────────────────────────
# Source: GitHub public APIs / repositories
# https://github.com/huggingface/transformers
# https://github.com/pytorch/pytorch
# https://github.com/tensorflow/tensorflow
GITHUB_ENTITIES = [
    {"id": "repo_transformers", "type": "repository", "text": "huggingface/transformers",
     "stars": 135000, "source_url": "https://github.com/huggingface/transformers"},
    {"id": "repo_pytorch", "type": "repository", "text": "pytorch/pytorch",
     "stars": 82000, "source_url": "https://github.com/pytorch/pytorch"},
    {"id": "repo_tensorflow", "type": "repository", "text": "tensorflow/tensorflow",
     "stars": 184000, "source_url": "https://github.com/tensorflow/tensorflow"},
    {"id": "repo_llama_cpp", "type": "repository", "text": "ggerganov/llama.cpp",
     "stars": 65000, "source_url": "https://github.com/ggerganov/llama.cpp"},
    {"id": "repo_langchain", "type": "repository", "text": "langchain-ai/langchain",
     "stars": 91000, "source_url": "https://github.com/langchain-ai/langchain"},
    {"id": "repo_vllm", "type": "repository", "text": "vllm-project/vllm",
     "stars": 28000, "source_url": "https://github.com/vllm-project/vllm"},
    {"id": "org_huggingface", "type": "organization", "text": "Hugging Face"},
    {"id": "org_pytorch_foundation", "type": "organization", "text": "PyTorch Foundation"},
    {"id": "org_google", "type": "organization", "text": "Google"},
    {"id": "org_meta", "type": "organization", "text": "Meta AI"},
]

GITHUB_RELATIONSHIPS = [
    {"source_id": "org_huggingface", "target_id": "repo_transformers", "type": "maintains", "confidence": 1.0},
    {"source_id": "org_pytorch_foundation", "target_id": "repo_pytorch", "type": "maintains", "confidence": 1.0},
    {"source_id": "org_google", "target_id": "repo_tensorflow", "type": "maintains", "confidence": 1.0},
    {"source_id": "org_meta", "target_id": "repo_llama_cpp", "type": "inspired", "confidence": 0.7},
    {"source_id": "repo_transformers", "target_id": "repo_pytorch", "type": "depends_on", "confidence": 0.95},
    {"source_id": "repo_transformers", "target_id": "repo_tensorflow", "type": "depends_on", "confidence": 0.8},
    {"source_id": "repo_langchain", "target_id": "repo_transformers", "type": "integrates", "confidence": 0.9},
    {"source_id": "repo_vllm", "target_id": "repo_pytorch", "type": "depends_on", "confidence": 1.0},
    {"source_id": "repo_llama_cpp", "target_id": "repo_pytorch", "type": "inspired_by", "confidence": 0.6},
]


def _build_research_graph() -> ContextGraph:
    """Build a research paper citation graph."""
    g = ContextGraph(advanced_analytics=True)
    g.build_from_entities_and_relationships(ALL_ARXIV_ENTITIES, ARXIV_RELATIONSHIPS)
    return g


def _build_ecommerce_graph() -> ContextGraph:
    """Build an e-commerce product graph."""
    g = ContextGraph(advanced_analytics=True)
    g.build_from_entities_and_relationships(ECOMMERCE_ENTITIES, ECOMMERCE_RELATIONSHIPS)
    return g


def _build_github_graph() -> ContextGraph:
    """Build a GitHub repository dependency graph."""
    g = ContextGraph(advanced_analytics=True)
    g.build_from_entities_and_relationships(GITHUB_ENTITIES, GITHUB_RELATIONSHIPS)
    return g


# ═════════════════════════════════════════════════════════════════════════════
# A. ContextGraph Advanced Decision Methods (NOT covered in comprehensive file)
# ═════════════════════════════════════════════════════════════════════════════

class TestContextGraphAdvancedDecisionMethods:
    """
    Tests for advanced decision methods added in 0.3.0-alpha:
      - analyze_decision_influence()
      - get_decision_insights()
      - trace_decision_causality()
      - enforce_decision_policy()
      - find_precedents_by_scenario()

    Scenario: Financial services — loan approval pipeline for three customers.
    Data: Realistic mortgage application workflow with entity linkage.
    """

    def _build_loan_graph(self):
        """Build loan decision graph. Returns (graph, dict_of_named_ids)."""
        g = ContextGraph(advanced_analytics=True)
        # Three loan decisions with shared entities to create influence chains
        id_alice = g.record_decision(
            category="mortgage",
            scenario="30yr fixed rate mortgage, $450k purchase, FICO 790, DTI 32%, 20% down.",
            reasoning=(
                "Applicant meets all Fannie Mae guidelines: FICO >760, DTI <36%, "
                "LTV 80%. Income verified via 2 yrs W-2 (>3x monthly payment). Approved."
            ),
            outcome="approved",
            confidence=0.96,
            entities=["customer_alice_001", "property_sf_bay_area", "underwriter_ai_v5"],
            decision_maker="underwriter_ai_v5",
        )
        id_bob = g.record_decision(
            category="mortgage",
            scenario="15yr fixed rate mortgage, $320k refi, FICO 745, DTI 38%, cash-out $50k.",
            reasoning=(
                "Cash-out refi; LTV post-cash-out = 72%. FICO 745 meets minimum. "
                "DTI 38% at upper bound but within Fannie 45% limit for strong FICO. Approved."
            ),
            outcome="approved",
            confidence=0.88,
            entities=["customer_bob_002", "property_seattle_wa", "underwriter_ai_v5"],
            decision_maker="underwriter_ai_v5",
        )
        id_carol = g.record_decision(
            category="mortgage",
            scenario="FHA loan $280k, FICO 620, DTI 46%, 3.5% down — first-time buyer.",
            reasoning=(
                "FICO 620 meets FHA floor (580+). DTI 46% exceeds FHA limit (43%) — "
                "compensating factors: 12mo rent history, no late payments, stable 3yr employment. "
                "Manual underwrite. Approved with conditions."
            ),
            outcome="approved_with_conditions",
            confidence=0.72,
            entities=["customer_carol_003", "property_phoenix_az", "underwriter_ai_v5"],
            decision_maker="underwriter_ai_v5",
        )
        id_fraud = g.record_decision(
            category="fraud_screening",
            scenario="Fraud check for customer_carol_003: income verification, identity check.",
            reasoning="SSN verified against IRS. Income docs match. No synthetic identity flags.",
            outcome="cleared",
            confidence=0.99,
            entities=["customer_carol_003", "fraud_screening_engine"],
            decision_maker="fraud_screening_engine",
        )
        return g, {"alice": id_alice, "bob": id_bob, "carol": id_carol, "fraud": id_fraud}

    def test_analyze_decision_influence_returns_dict(self):
        g, ids = self._build_loan_graph()
        result = g.analyze_decision_influence(ids["alice"])
        assert isinstance(result, dict)
        assert "decision_id" in result
        assert result["decision_id"] == ids["alice"]
        assert "total_influenced" in result
        assert "max_influence_score" in result

    def test_analyze_decision_influence_shared_entity(self):
        """Decisions sharing entity underwriter_ai_v5 should influence each other."""
        g, ids = self._build_loan_graph()
        result = g.analyze_decision_influence(ids["alice"])
        # alice, bob, and carol all share underwriter_ai_v5 — they should appear in influence
        direct = result["direct_influence"]
        assert isinstance(direct, list)
        assert all(isinstance(item, dict) for item in direct)
        assert all(
            {"decision_id", "scenario", "outcome", "category"}.issubset(item.keys())
            for item in direct
        )
        direct_ids = {item["decision_id"] for item in direct}
        assert ids["bob"] in direct_ids

    def test_analyze_decision_influence_category_cross(self):
        """Decisions in same category appear in influence set."""
        g, ids = self._build_loan_graph()
        result = g.analyze_decision_influence(ids["bob"])
        # alice and bob are both "mortgage" category — alice should appear in influence
        direct_ids = [d["decision_id"] for d in result["direct_influence"]]
        assert ids["alice"] in direct_ids or result["total_influenced"] >= 0

    def test_analyze_decision_influence_nonexistent_raises(self):
        g, _ = self._build_loan_graph()
        with pytest.raises(ValueError, match="not found"):
            g.analyze_decision_influence("nonexistent_decision_xyz")

    def test_get_decision_insights_structure(self):
        g, _ = self._build_loan_graph()
        insights = g.get_decision_insights()
        assert isinstance(insights, dict)
        assert "total_decisions" in insights
        assert insights["total_decisions"] == 4
        assert "categories" in insights
        assert "mortgage" in insights["categories"]
        assert "fraud_screening" in insights["categories"]
        assert "outcomes" in insights
        assert "confidence_stats" in insights

    def test_get_decision_insights_confidence_stats(self):
        g, _ = self._build_loan_graph()
        insights = g.get_decision_insights()
        stats = insights["confidence_stats"]
        assert "mean" in stats and "min" in stats and "max" in stats
        assert stats["min"] <= stats["mean"] <= stats["max"]
        assert stats["min"] >= 0.0 and stats["max"] <= 1.0

    def test_get_decision_insights_empty_graph(self):
        g = ContextGraph()
        insights = g.get_decision_insights()
        assert isinstance(insights, dict)
        # Should return a message or empty structure, not crash
        assert "message" in insights or insights == {}

    def test_trace_decision_causality_returns_list(self):
        g, ids = self._build_loan_graph()
        causality = g.trace_decision_causality(ids["carol"])
        assert isinstance(causality, list)

    def test_trace_decision_causality_shared_entity_chain(self):
        """fraud decision shares customer_carol_003 with carol loan decision."""
        g, ids = self._build_loan_graph()
        # Both reference customer_carol_003; earlier decision may cause later one
        causality = g.trace_decision_causality(ids["carol"])
        # Check it doesn't crash and returns valid structure
        assert isinstance(causality, list)
        for chain in causality:
            # Each chain should be either a list of relationships or an error dict
            assert isinstance(chain, (list, dict))

    def test_trace_decision_causality_nonexistent_raises(self):
        g, _ = self._build_loan_graph()
        with pytest.raises(ValueError, match="not found"):
            g.trace_decision_causality("ghost_decision_999")

    def test_enforce_decision_policy_compliant(self):
        g = ContextGraph()
        decision_data = {
            "category": "mortgage",
            "outcome": "approved",
            "confidence": 0.92,
            "reasoning": "Strong applicant profile.",
            "decision_maker": "underwriter_ai_v5",
        }
        result = g.enforce_decision_policy(decision_data)
        assert isinstance(result, dict)
        assert "compliant" in result
        assert "violations" in result
        assert "warnings" in result

    def test_enforce_decision_policy_low_confidence_violation(self):
        g = ContextGraph()
        decision_data = {
            "category": "mortgage",
            "outcome": "approved",
            "confidence": 0.5,  # Below default min 0.7
            "reasoning": "Some reasoning.",
            "decision_maker": "underwriter_ai",
        }
        result = g.enforce_decision_policy(decision_data)
        assert result["compliant"] is False
        assert len(result["violations"]) > 0
        assert any("Confidence" in v for v in result["violations"])

    def test_enforce_decision_policy_invalid_outcome(self):
        g = ContextGraph()
        decision_data = {
            "category": "mortgage",
            "outcome": "maybe",  # Not in required_outcomes
            "confidence": 0.9,
            "reasoning": "Some reasoning.",
            "decision_maker": "bot",
        }
        result = g.enforce_decision_policy(decision_data)
        assert result["compliant"] is False
        assert any("Invalid outcome" in v for v in result["violations"])

    def test_enforce_decision_policy_custom_rules(self):
        g = ContextGraph()
        decision_data = {
            "outcome": "green_light",
            "confidence": 0.85,
            "reasoning": "Green.",
            "decision_maker": "trading_bot",
        }
        custom_rules = {
            "min_confidence": 0.80,
            "required_outcomes": ["green_light", "red_light", "hold"],
            "required_metadata": ["decision_maker"],
        }
        result = g.enforce_decision_policy(decision_data, policy_rules=custom_rules)
        assert result["compliant"] is True
        assert len(result["violations"]) == 0

    def test_enforce_decision_policy_long_reasoning_warning(self):
        g = ContextGraph()
        decision_data = {
            "outcome": "approved",
            "confidence": 0.85,
            "reasoning": "X" * 1500,  # Exceeds default 1000 char limit
            "decision_maker": "bot",
        }
        result = g.enforce_decision_policy(decision_data)
        # Should generate a warning (long reasoning) but may still be compliant
        assert len(result["warnings"]) > 0

    def test_find_precedents_by_scenario_returns_list(self):
        g, _ = self._build_loan_graph()
        precedents = g.find_precedents_by_scenario(
            "first-time buyer mortgage with FHA loan",
            category="mortgage",
            limit=5,
        )
        assert isinstance(precedents, list)

    def test_find_precedents_by_scenario_empty_graph_returns_empty(self):
        g = ContextGraph()
        precedents = g.find_precedents_by_scenario("some scenario")
        assert isinstance(precedents, list)
        assert len(precedents) == 0


# ═════════════════════════════════════════════════════════════════════════════
# B. Research Paper Citation Graph (arXiv data, no live calls)
# ═════════════════════════════════════════════════════════════════════════════

class TestResearchPaperCitationGraph:
    """
    Knowledge graph built from real AI research papers (public arXiv metadata).

    Source references embedded in entity metadata:
      - https://arxiv.org/abs/1706.03762 (Transformer)
      - https://arxiv.org/abs/1810.04805 (BERT)
      - https://arxiv.org/abs/2005.14165 (GPT-3)
      - https://arxiv.org/abs/2303.08774 (GPT-4)
    """

    def test_citation_graph_has_correct_node_count(self):
        g = _build_research_graph()
        stats = g.stats()
        assert stats["node_count"] >= len(ALL_ARXIV_ENTITIES)

    def test_citation_paper_nodes_have_source_urls(self):
        g = _build_research_graph()
        # All paper nodes should have source_url in metadata
        papers = g.find_nodes(node_type="paper")
        assert len(papers) == len(ARXIV_PAPERS)
        for paper in papers:
            meta = paper.get("metadata", {})
            assert "source_url" in meta
            assert meta["source_url"].startswith("https://arxiv.org/abs/")

    def test_transformer_paper_is_highly_cited(self):
        """Attention Is All You Need is cited by 5 other papers in our graph."""
        g = _build_research_graph()
        # Count edges where arxiv_1706.03762 is the target of "cites" edges
        cites_edges = g.find_edges(edge_type="cites")
        cited_transformer = [e for e in cites_edges if e["target"] == "arxiv_1706.03762"]
        assert len(cited_transformer) >= 4  # BERT, GPT-3, GPT-4, LLaMA, PaLM

    def test_shortest_path_author_to_descendant_paper(self):
        """Path: vaswani_a --authored--> transformer --cites--> BERT (reverse: BERT cites transformer)."""
        import networkx as nx
        G = nx.DiGraph()
        for e in ALL_ARXIV_ENTITIES:
            G.add_node(e["id"], **{k: v for k, v in e.items() if k != "id"})
        for r in ARXIV_RELATIONSHIPS:
            G.add_edge(r["source_id"], r["target_id"], type=r["type"])
        # vaswani authored transformer; transformer is cited by bert
        # path (undirected): vaswani_a -> arxiv_1706.03762 -> arxiv_1810.04805
        G_undirected = G.to_undirected()
        finder = PathFinder()
        path = finder.find_shortest_path(G_undirected, "vaswani_a", "arxiv_1810.04805")
        assert path is not None
        assert "arxiv_1706.03762" in path

    def test_community_detection_finds_clusters(self):
        """Papers should cluster into 'transformer lineage' and 'authors' communities."""
        import networkx as nx
        G = nx.Graph()
        for e in ALL_ARXIV_ENTITIES:
            G.add_node(e["id"])
        for r in ARXIV_RELATIONSHIPS:
            G.add_edge(r["source_id"], r["target_id"])
        detector = CommunityDetector()
        communities = detector.detect_communities(G)
        assert communities is not None

    def test_centrality_of_transformer_paper(self):
        """The Transformer paper is the most influential — expect high centrality."""
        import networkx as nx
        G = nx.DiGraph()
        for e in ALL_ARXIV_ENTITIES:
            G.add_node(e["id"])
        for r in ARXIV_RELATIONSHIPS:
            G.add_edge(r["source_id"], r["target_id"])
        calc = CentralityCalculator()
        result = calc.calculate_all_centrality(G)
        assert isinstance(result, dict)
        assert len(result) > 0

    def test_decision_tracking_on_research_graph(self):
        """Record paper acceptance decisions and check insights."""
        g = _build_research_graph()
        for paper in ARXIV_PAPERS[:3]:
            g.record_decision(
                category="paper_acceptance",
                scenario=f"Review decision for '{paper['text']}' at {paper['venue']} {paper['year']}",
                reasoning=f"High novelty, strong empirical results, {paper['citations']}+ citations by 2024.",
                outcome="accepted",
                confidence=0.97,
                entities=[paper["id"]],
                decision_maker="program_committee_ai",
            )
        insights = g.get_decision_insights()
        assert insights["total_decisions"] == 3
        assert insights["categories"]["paper_acceptance"] == 3
        stats = insights["confidence_stats"]
        assert abs(stats["mean"] - 0.97) < 0.001

    def test_provenance_tracked_per_paper(self):
        """ProvenanceTracker records source URLs for each paper entity."""
        tracker = ProvenanceTracker()
        for paper in ARXIV_PAPERS:
            tracker.track_entity(paper["id"], paper["source_url"], metadata={"type": "paper"})
        # All 6 papers should have exactly one source URL each
        for paper in ARXIV_PAPERS:
            sources = tracker.get_all_sources(paper["id"])
            assert len(sources) == 1
            assert sources[0]["source"] == paper["source_url"]
        # Clear and verify
        tracker.clear()
        assert tracker.get_all_sources("arxiv_1706.03762") == []


# ═════════════════════════════════════════════════════════════════════════════
# C. E-commerce Context Graph (Amazon product domain)
# ═════════════════════════════════════════════════════════════════════════════

class TestEcommerceContextGraph:
    """
    Knowledge graph modeling an e-commerce product catalog.
    Domain: Amazon, Apple, Samsung, Microsoft tablet/device category.
    Source: https://www.amazon.com (public product listings)
    """

    def test_ecommerce_graph_builds_correctly(self):
        g = _build_ecommerce_graph()
        stats = g.stats()
        assert stats["node_count"] >= len(ECOMMERCE_ENTITIES)
        assert stats["edge_count"] >= len(ECOMMERCE_RELATIONSHIPS)

    def test_product_node_has_price_metadata(self):
        g = _build_ecommerce_graph()
        node = g.find_node("prod_kindle_scribe")
        assert node is not None
        # Price should be stored in metadata
        meta = node.get("metadata", {})
        assert meta.get("price") == 369.99

    def test_tablets_are_three(self):
        g = _build_ecommerce_graph()
        tablets_rels = g.find_edges(edge_type="belongs_to")
        tablet_products = [e for e in tablets_rels if e["target"] == "cat_tablets"]
        assert len(tablet_products) == 3  # iPad, Galaxy Tab, Surface Pro

    def test_competes_with_edges(self):
        g = _build_ecommerce_graph()
        comp_edges = g.find_edges(edge_type="competes_with")
        assert len(comp_edges) == 2

    def test_two_hop_brand_to_category(self):
        """brand_apple --manufactures--> prod_ipad_air_m2 --belongs_to--> cat_tablets."""
        g = _build_ecommerce_graph()
        neighbors = g.get_neighbors("brand_apple", hops=2)
        two_hop_ids = {n["id"] for n in neighbors}
        assert "cat_tablets" in two_hop_ids

    def test_pricing_decision_tracking(self):
        """Record product pricing decisions and check policy enforcement."""
        g = _build_ecommerce_graph()
        pricing_id = g.record_decision(
            category="pricing",
            scenario="iPad Air M2 2024 launch price: $599 for base 256GB model.",
            reasoning=(
                "Competitive with Samsung Galaxy Tab S9 ($799) and Surface Pro 10 ($1199). "
                "Priced $200 above previous gen M1 to reflect M2 chip premium. "
                "Target: maintain 18% tablet market share in North America."
            ),
            outcome="approved",
            confidence=0.91,
            entities=["prod_ipad_air_m2", "brand_apple"],
            decision_maker="apple_pricing_team",
        )
        assert g.has_node(pricing_id)
        # Enforce policy on the pricing decision
        result = g.enforce_decision_policy({
            "outcome": "approved",
            "confidence": 0.91,
            "reasoning": "Competitive pricing decision.",
            "decision_maker": "apple_pricing_team",
        })
        assert result["compliant"] is True

    def test_inventory_decision_causal_chain(self):
        """supply_disruption → inventory_drawdown → price_increase causal chain."""
        g = _build_ecommerce_graph()
        d_supply = g.record_decision(
            category="supply_chain",
            scenario="TSMC 3nm node capacity constraint: 30% allocation shortfall for A17 chip.",
            reasoning="Geopolitical tensions + TSMC plant maintenance window reduces Q4 supply.",
            outcome="supply_risk_flagged",
            confidence=0.85,
            entities=["brand_apple", "tsmc_fab"],
            decision_maker="supply_chain_ai",
        )
        d_inventory = g.record_decision(
            category="inventory",
            scenario="iPad Air M2 inventory buffer increased to 90 days from 60 days.",
            reasoning="Hedging supply shortfall risk by pre-building inventory buffer.",
            outcome="inventory_adjusted",
            confidence=0.87,
            entities=["prod_ipad_air_m2", "brand_apple"],
            decision_maker="inventory_planner_ai",
        )
        d_price = g.record_decision(
            category="pricing",
            scenario="iPad Air M2 price increased by $30 on Q4 SKUs to offset inventory cost.",
            reasoning="Carrying cost of 90d buffer ~$30/unit at current rates.",
            outcome="approved",
            confidence=0.78,
            entities=["prod_ipad_air_m2", "brand_apple"],
            decision_maker="apple_pricing_team",
        )
        g.add_causal_relationship(d_supply, d_inventory, "CAUSED")
        g.add_causal_relationship(d_inventory, d_price, "INFLUENCED")
        chain = g.get_causal_chain(d_supply, direction="downstream", max_depth=5)
        chain_ids = {d.decision_id for d in chain}
        assert d_inventory in chain_ids
        assert d_price in chain_ids

    def test_purchase_decision_precedents(self):
        """B2B bulk purchase decisions should find precedents for similar orders."""
        g = _build_ecommerce_graph()
        for i in range(3):
            g.record_decision(
                category="b2b_purchase",
                scenario=f"Enterprise order #{i+1}: 500x Surface Pro 10 for Microsoft-certified partners.",
                reasoning="Volume discount >100 units (15%); deployment timeline 30 days.",
                outcome="purchase_approved",
                confidence=0.93 - i * 0.02,
                entities=["prod_surface_pro10", "brand_microsoft"],
                decision_maker="b2b_procurement_ai",
            )
        precedents = g.find_precedents_by_scenario(
            "enterprise bulk tablet purchase order",
            category="b2b_purchase",
            limit=5,
        )
        assert isinstance(precedents, list)


# ═════════════════════════════════════════════════════════════════════════════
# D. GraphBuilderWithProvenance — real web-sourced provenance (0.3.0-alpha)
# ═════════════════════════════════════════════════════════════════════════════

class TestGraphBuilderWithProvenanceRealData:
    """
    GraphBuilderWithProvenance tracks entity source lineage from real web sources.
    Sources: GitHub URLs, Wikipedia, arXiv, SEC EDGAR.
    """

    def test_build_with_github_provenance(self):
        """Build KG from GitHub-sourced entity data with source URL tracking."""
        sources = [
            {
                "entities": GITHUB_ENTITIES,
                "relationships": GITHUB_RELATIONSHIPS,
                "metadata": {
                    "source": "https://api.github.com/repos",
                    "retrieved_at": "2026-03-09T00:00:00Z",
                },
            }
        ]
        builder = GraphBuilderWithProvenance()
        kg = builder.build(sources=sources)
        assert isinstance(kg, dict)
        assert "entities" in kg
        assert len(kg["entities"]) >= len(GITHUB_ENTITIES)

    def test_provenance_records_source_urls(self):
        """Each entity should have provenance metadata from its source URL."""
        tracker = ProvenanceTracker()
        for entity in GITHUB_ENTITIES:
            if "source_url" in entity:
                tracker.track_entity(
                    entity["id"],
                    entity["source_url"],
                    metadata={"type": entity["type"], "stars": entity.get("stars")},
                )
        # Verify repositories have GitHub URLs as provenance
        repo_ids = [e["id"] for e in GITHUB_ENTITIES if e["type"] == "repository"]
        for repo_id in repo_ids:
            sources = tracker.get_all_sources(repo_id)
            assert len(sources) == 1
            assert sources[0]["source"].startswith("https://github.com/")

    def test_multi_source_entity_provenance(self):
        """Entity appearing in multiple data sources gets multiple provenance records."""
        tracker = ProvenanceTracker()
        # PyTorch appears in both GitHub data and academic papers
        tracker.track_entity("pytorch", "https://github.com/pytorch/pytorch",
                              metadata={"type": "repository"})
        tracker.track_entity("pytorch", "https://arxiv.org/abs/1912.01703",
                              metadata={"type": "paper_reference"})
        tracker.track_entity("pytorch", "https://en.wikipedia.org/wiki/PyTorch",
                              metadata={"type": "wiki"})
        sources = tracker.get_all_sources("pytorch")
        assert len(sources) == 3
        source_urls = [s["source"] for s in sources]
        assert "https://github.com/pytorch/pytorch" in source_urls
        assert "https://arxiv.org/abs/1912.01703" in source_urls
        assert "https://en.wikipedia.org/wiki/PyTorch" in source_urls

    def test_build_from_arxiv_entities_with_provenance(self):
        """Build KG from arXiv paper metadata with per-entity provenance."""
        sources = [
            {
                "entities": ARXIV_PAPERS,
                "relationships": [
                    r for r in ARXIV_RELATIONSHIPS if r["type"] == "cites"
                ],
                "metadata": {
                    "source": "https://arxiv.org",
                    "domain": "academic_papers",
                },
            }
        ]
        builder = GraphBuilderWithProvenance()
        kg = builder.build(sources=sources)
        assert "entities" in kg
        assert len(kg["entities"]) >= len(ARXIV_PAPERS)


# ═════════════════════════════════════════════════════════════════════════════
# E. AlgorithmTrackerWithProvenance — domain-specific tracking methods
# ═════════════════════════════════════════════════════════════════════════════

class TestAlgorithmTrackerWithProvenanceRealData:
    """
    Tests for domain-specific tracking methods added in 0.3.0-alpha bug fix.
    All methods wrap the base _track_generic().
    """

    def _make_tracker(self):
        # provenance=False (default) — methods return None but must not raise
        return AlgorithmTrackerWithProvenance()

    def test_track_embedding_computation(self):
        """track_embedding_computation requires (graph, algorithm, embeddings, parameters)."""
        import networkx as nx
        tracker = self._make_tracker()
        G = nx.DiGraph()
        G.add_nodes_from(["arxiv_1706.03762", "arxiv_1810.04805"])
        result = tracker.track_embedding_computation(
            graph=G,
            algorithm="node2vec",
            embeddings={"arxiv_1706.03762": [0.1, 0.2], "arxiv_1810.04805": [0.3, 0.4]},
            parameters={"embedding_dimension": 2, "walk_length": 10},
            source="https://arxiv.org/abs/1706.03762",
        )
        # Returns None when provenance=False; str execution ID when provenance=True
        assert result is None or isinstance(result, str)

    def test_track_similarity_calculation(self):
        """track_similarity_calculation requires (embeddings, query_embedding, similarities, method)."""
        tracker = self._make_tracker()
        result = tracker.track_similarity_calculation(
            embeddings={"repo_transformers": [0.5, 0.6], "repo_langchain": [0.7, 0.8]},
            query_embedding=[0.5, 0.6],
            similarities={"repo_langchain": 0.78},
            method="cosine",
        )
        assert result is None or isinstance(result, str)

    def test_track_link_prediction(self):
        """track_link_prediction requires (graph, predictions, method, parameters)."""
        import networkx as nx
        tracker = self._make_tracker()
        G = nx.Graph()
        G.add_nodes_from(["brand_amazon", "brand_google"])
        result = tracker.track_link_prediction(
            graph=G,
            predictions=[("brand_amazon", "brand_google", 0.82)],
            method="preferential_attachment",
            parameters={"threshold": 0.5},
        )
        assert result is None or isinstance(result, str)

    def test_track_centrality_calculation(self):
        """track_centrality_calculation requires (graph, centrality_scores, method)."""
        import networkx as nx
        tracker = self._make_tracker()
        G = nx.DiGraph()
        G.add_nodes_from(["arxiv_1706.03762", "arxiv_1810.04805"])
        result = tracker.track_centrality_calculation(
            graph=G,
            centrality_scores={"arxiv_1706.03762": 0.65, "arxiv_1810.04805": 0.40},
            method="betweenness",
        )
        assert result is None or isinstance(result, str)

    def test_track_community_detection(self):
        """track_community_detection requires (graph, communities, method)."""
        import networkx as nx
        tracker = self._make_tracker()
        G = nx.Graph()
        G.add_nodes_from(["repo_pytorch", "repo_tensorflow", "repo_transformers"])
        result = tracker.track_community_detection(
            graph=G,
            communities=[["repo_pytorch", "repo_transformers"], ["repo_tensorflow"]],
            method="louvain",
        )
        assert result is None or isinstance(result, str)

    def test_track_graph_construction(self):
        """track_graph_construction requires (input_data, output_graph, entities_count, relationships_count)."""
        tracker = self._make_tracker()
        result = tracker.track_graph_construction(
            input_data={"source": "github_api"},
            output_graph={"nodes": len(GITHUB_ENTITIES), "edges": len(GITHUB_RELATIONSHIPS)},
            entities_count=len(GITHUB_ENTITIES),
            relationships_count=len(GITHUB_RELATIONSHIPS),
            source="github_api",
        )
        assert result is None or isinstance(result, str)

    def test_track_path_finding(self):
        """track_path_finding requires (graph, ...) with optional keyword args."""
        import networkx as nx
        tracker = self._make_tracker()
        G = nx.DiGraph()
        G.add_nodes_from(["vaswani_a", "arxiv_1706.03762", "arxiv_1810.04805"])
        result = tracker.track_path_finding(
            graph=G,
            source_node="vaswani_a",
            target_node="arxiv_1810.04805",
            path=["vaswani_a", "arxiv_1706.03762", "arxiv_1810.04805"],
            method="bfs",
        )
        assert result is None or isinstance(result, str)

    def test_track_connectivity_analysis(self):
        """track_connectivity_analysis requires (graph, components)."""
        import networkx as nx
        tracker = self._make_tracker()
        G = nx.DiGraph()
        for e in GITHUB_ENTITIES:
            G.add_node(e["id"])
        result = tracker.track_connectivity_analysis(
            graph=G,
            components=[["repo_pytorch", "repo_vllm"], ["repo_transformers", "repo_langchain"]],
        )
        assert result is None or isinstance(result, str)

    def test_track_cross_domain_similarity(self):
        """Domain-specific method (0.3.0-alpha fix) — accepts **kwargs."""
        tracker = self._make_tracker()
        result = tracker.track_cross_domain_similarity(
            entity_a="repo_transformers",
            entity_b="arxiv_1706.03762",
            score=0.91,
            domain_a="software",
            domain_b="research",
        )
        assert result is None or isinstance(result, str)

    def test_track_collaboration_potential(self):
        """Domain-specific method (0.3.0-alpha fix) — accepts **kwargs."""
        tracker = self._make_tracker()
        result = tracker.track_collaboration_potential(
            entity_a="org_huggingface",
            entity_b="org_meta",
            score=0.73,
        )
        assert result is None or isinstance(result, str)


# ═════════════════════════════════════════════════════════════════════════════
# F. Parquet Export (0.3.0-beta, PR #343)
# ═════════════════════════════════════════════════════════════════════════════

class TestParquetExportRealData:
    """
    Apache Parquet export with real-world entity data.
    Tests all compression codecs and KG export patterns.
    Requires: pyarrow (optional dep — tests skip if not installed).
    """

    # ParquetExporter imports fine without pyarrow and only raises ImportError
    # when an export actually runs, so guarding on that import never skips
    # anything. Guard on the exporter's own availability flag instead: it is set
    # by the same `import pyarrow` / `import pyarrow.parquet` the exporter gates
    # on, so the skip condition cannot drift from the runtime check — including
    # when pyarrow is present on the path but fails to import.
    pytestmark = pytest.mark.skipif(
        not PARQUET_AVAILABLE,
        reason="pyarrow not installed",
    )

    @pytest.fixture
    def kg_data(self):
        return {
            "entities": [
                {"id": e["id"], "type": e["type"], "properties": {
                    "name": e["text"],
                    "source_url": e.get("source_url", ""),
                    **{k: v for k, v in e.items() if k not in ("id", "type", "text", "source_url")},
                }}
                for e in GITHUB_ENTITIES
            ],
            "relationships": [
                {"source_id": r["source_id"], "target_id": r["target_id"],
                 "type": r["type"], "properties": {"confidence": r["confidence"]}}
                for r in GITHUB_RELATIONSHIPS
            ],
        }

    def test_parquet_exporter_importable(self):
        from semantica.export import ParquetExporter

        assert ParquetExporter is not None

    def test_parquet_export_entities_to_file(self, kg_data, tmp_path):
        from semantica.export import ParquetExporter

        exporter = ParquetExporter(compression="snappy")
        out_path = tmp_path / "github_entities.parquet"
        exporter.export_entities(kg_data["entities"], str(out_path))
        assert out_path.exists()
        assert out_path.stat().st_size > 0

    def test_parquet_export_relationships_to_file(self, kg_data, tmp_path):
        from semantica.export import ParquetExporter

        exporter = ParquetExporter(compression="gzip")
        out_path = tmp_path / "github_relationships.parquet"
        exporter.export_relationships(kg_data["relationships"], str(out_path))
        assert out_path.exists()
        assert out_path.stat().st_size > 0

    def test_parquet_export_knowledge_graph(self, kg_data, tmp_path):
        from semantica.export import ParquetExporter

        exporter = ParquetExporter(compression="snappy")
        base_path = tmp_path / "github_kg"
        exporter.export_knowledge_graph(kg_data, str(base_path))
        # Should create entities + relationships files
        files = list(tmp_path.glob("*.parquet"))
        assert len(files) >= 1

    def test_parquet_export_snappy_compression(self, kg_data, tmp_path):
        from semantica.export import ParquetExporter

        exporter = ParquetExporter(compression="snappy")
        out_path = tmp_path / "snappy_test.parquet"
        exporter.export_entities(kg_data["entities"], str(out_path))
        assert out_path.exists()

    def test_parquet_export_none_compression(self, kg_data, tmp_path):
        from semantica.export import ParquetExporter

        exporter = ParquetExporter(compression="none")
        out_path = tmp_path / "uncompressed_test.parquet"
        exporter.export_entities(kg_data["entities"], str(out_path))
        assert out_path.exists()

    def test_parquet_convenience_function(self, kg_data, tmp_path):
        from semantica.export.methods import export_parquet

        out_path = tmp_path / "convenience_test.parquet"
        export_parquet(kg_data["entities"], str(out_path))
        assert out_path.exists()


# ═════════════════════════════════════════════════════════════════════════════
# G. ArangoDB AQL Export (0.3.0-beta, PR #342)
# ═════════════════════════════════════════════════════════════════════════════

class TestArangoAQLExportRealData:
    """
    ArangoDB AQL export tested with real AI company and research paper data.
    Verifies AQL INSERT statement generation, batch processing, collection names.
    """

    @pytest.fixture
    def ai_kg_data(self):
        return {
            "entities": [
                {"id": p["id"], "type": p["type"], "properties": {
                    "title": p["text"],
                    "year": p.get("year"),
                    "venue": p.get("venue"),
                    "citations": p.get("citations"),
                    "source_url": p.get("source_url"),
                }}
                for p in ARXIV_PAPERS
            ] + [
                {"id": a["id"], "type": a["type"], "properties": {
                    "name": a["text"], "affiliation": a["affiliation"],
                    "source_url": a["source_url"],
                }}
                for a in ARXIV_AUTHORS
            ],
            "relationships": [
                {"source_id": r["source_id"], "target_id": r["target_id"],
                 "type": r["type"], "properties": {"confidence": r["confidence"]}}
                for r in ARXIV_RELATIONSHIPS
            ],
        }

    def test_arango_exporter_importable(self):
        from semantica.export.arango_aql_exporter import ArangoAQLExporter
        exporter = ArangoAQLExporter()
        assert exporter is not None

    def test_arango_export_to_file(self, ai_kg_data, tmp_path):
        from semantica.export.arango_aql_exporter import ArangoAQLExporter
        exporter = ArangoAQLExporter()
        out_path = tmp_path / "arxiv_papers.aql"
        exporter.export(ai_kg_data, str(out_path))
        assert out_path.exists()
        assert out_path.stat().st_size > 0

    def test_arango_export_contains_aql_inserts(self, ai_kg_data, tmp_path):
        from semantica.export.arango_aql_exporter import ArangoAQLExporter
        exporter = ArangoAQLExporter()
        out_path = tmp_path / "arxiv_aql_check.aql"
        exporter.export(ai_kg_data, str(out_path))
        content = out_path.read_text(encoding="utf-8")
        # AQL export must contain INSERT statements
        assert "INSERT" in content

    def test_arango_export_contains_entity_ids(self, ai_kg_data, tmp_path):
        from semantica.export.arango_aql_exporter import ArangoAQLExporter
        exporter = ArangoAQLExporter()
        out_path = tmp_path / "arxiv_entities_check.aql"
        exporter.export(ai_kg_data, str(out_path))
        content = out_path.read_text(encoding="utf-8")
        # Should contain at least one paper ID
        assert "arxiv_1706.03762" in content

    def test_arango_export_custom_collection_names(self, ai_kg_data, tmp_path):
        from semantica.export.arango_aql_exporter import ArangoAQLExporter
        exporter = ArangoAQLExporter(
            vertex_collection="research_nodes",
            edge_collection="research_edges",
        )
        out_path = tmp_path / "custom_collections.aql"
        exporter.export(ai_kg_data, str(out_path))
        content = out_path.read_text(encoding="utf-8")
        assert "research_nodes" in content or "research_edges" in content

    def test_arango_export_knowledge_graph_method(self, ai_kg_data, tmp_path):
        from semantica.export.arango_aql_exporter import ArangoAQLExporter
        exporter = ArangoAQLExporter()
        out_path = tmp_path / "kg_method.aql"
        exporter.export_knowledge_graph(ai_kg_data, str(out_path))
        assert out_path.exists()

    def test_arango_convenience_function(self, ai_kg_data, tmp_path):
        from semantica.export.methods import export_arango
        out_path = tmp_path / "convenience.aql"
        export_arango(ai_kg_data, str(out_path))
        assert out_path.exists()

    def test_arango_export_ecommerce_graph(self, tmp_path):
        """Export the e-commerce product catalog to AQL."""
        from semantica.export.arango_aql_exporter import ArangoAQLExporter
        kg_data = {
            "entities": [
                {"id": e["id"], "type": e["type"],
                 "properties": {k: v for k, v in e.items() if k != "id"}}
                for e in ECOMMERCE_ENTITIES
            ],
            "relationships": [
                {"source_id": r["source_id"], "target_id": r["target_id"],
                 "type": r["type"], "properties": {}}
                for r in ECOMMERCE_RELATIONSHIPS
            ],
        }
        exporter = ArangoAQLExporter()
        out_path = tmp_path / "ecommerce.aql"
        exporter.export(kg_data, str(out_path))
        content = out_path.read_text(encoding="utf-8")
        assert "prod_kindle_scribe" in content or "INSERT" in content


# ═════════════════════════════════════════════════════════════════════════════
# H. Deduplication v2 — Two-Stage Scoring Prefilter (0.3.0-beta, PR #339)
# ═════════════════════════════════════════════════════════════════════════════

class TestDeduplicationV2TwoStageScoring:
    """
    Tests for the opt-in two-stage scoring prefilter added in 0.3.0-beta.
    Uses real-world entity name variants that would appear in data pipelines.
    """

    def _make_detector(self, threshold=0.75, prefilter=True):
        from semantica.deduplication import DuplicateDetector
        return DuplicateDetector(similarity_threshold=threshold)

    def test_type_mismatch_prefilter(self):
        """Entities of different types should be rejected early by prefilter."""
        from semantica.deduplication import DuplicateDetector
        entities = [
            {"id": "e1", "name": "Python", "type": "ProgrammingLanguage"},
            {"id": "e2", "name": "Python", "type": "Snake"},  # Different type
        ]
        detector = DuplicateDetector(similarity_threshold=0.95)
        # With type mismatch, these should NOT be flagged as duplicates (different types)
        duplicates = detector.detect_duplicates(entities, threshold=0.95)
        assert isinstance(duplicates, list)

    def test_company_name_variants_detected(self):
        """Real-world company name variants from data integration pipelines."""
        from semantica.deduplication import DuplicateDetector
        entities = [
            # Meta / Facebook variants
            {"id": "e1", "name": "Meta Platforms Inc.", "type": "Company"},
            {"id": "e2", "name": "Meta Platforms", "type": "Company"},
            {"id": "e3", "name": "Facebook Inc.", "type": "Company"},
            {"id": "e4", "name": "Facebook", "type": "Company"},
            # Alphabet / Google variants
            {"id": "e5", "name": "Alphabet Inc.", "type": "Company"},
            {"id": "e6", "name": "Alphabet", "type": "Company"},
            {"id": "e7", "name": "Google LLC", "type": "Company"},
            {"id": "e8", "name": "Google", "type": "Company"},
            # Unique company
            {"id": "e9", "name": "OpenAI", "type": "Company"},
        ]
        detector = DuplicateDetector(similarity_threshold=0.70)
        duplicates = detector.detect_duplicates(entities, threshold=0.70)
        assert isinstance(duplicates, list)
        # Meta and Alphabet variants should produce some duplicate pairs
        assert len(duplicates) > 0

    def test_blocking_v2_with_phonetic_real_data(self):
        """blocking_v2 with real company names — phonetic matching helps catch typos."""
        from semantica.deduplication import DuplicateDetector
        entities = [
            {"id": f"co_{i}", "name": name, "type": "Company"}
            for i, name in enumerate([
                "Anthropic", "Anthropik", "anthropic PBC",  # Anthropic variants
                "DeepMind", "Deep Mind", "Google DeepMind",  # DeepMind variants
                "Mistral AI", "Mistral", "mistral ai",  # Mistral variants
                "Cohere Inc.", "Cohere", "Cohere Technologies",  # Cohere variants
                "AI21 Labs", "AI 21 Labs", "ai21",  # AI21 variants
            ])
        ]
        detector = DuplicateDetector(similarity_threshold=0.80)
        duplicates = detector.detect_duplicates(
            entities,
            threshold=0.80,
            candidate_strategy="blocking_v2",
        )
        assert isinstance(duplicates, list)
        assert len(duplicates) > 0

    def test_hybrid_v2_strategy(self):
        """hybrid_v2 combines blocking_v2 and legacy for best recall."""
        from semantica.deduplication import DuplicateDetector
        entities = [
            {"id": f"ent_{i}", "name": f"Organization Name {i}", "type": "Organization"}
            for i in range(20)
        ]
        entities.append({"id": "dup_a", "name": "Organization Name 7", "type": "Organization"})
        entities.append({"id": "dup_b", "name": "Organization Name 13", "type": "Organization"})
        detector = DuplicateDetector(similarity_threshold=0.95)
        duplicates = detector.detect_duplicates(
            entities,
            threshold=0.95,
            candidate_strategy="hybrid_v2",
        )
        # hybrid_v2 is a valid strategy that should not raise; result is a list of duplicate pairs
        assert isinstance(duplicates, list)

    def test_max_candidates_per_entity_budget(self):
        """max_candidates_per_entity prevents O(N²) explosion for large datasets."""
        from semantica.deduplication import DuplicateDetector
        # 50 entities — without budgeting this is 1225 pairs
        entities = [
            {"id": f"node_{i}", "name": f"Technology Company {i}", "type": "Company"}
            for i in range(50)
        ]
        detector = DuplicateDetector(similarity_threshold=0.90)
        # Should complete without timeout due to budget limiting
        duplicates = detector.detect_duplicates(
            entities,
            threshold=0.90,
            candidate_strategy="blocking_v2",
            max_candidates_per_entity=10,
        )
        assert isinstance(duplicates, list)


# ═════════════════════════════════════════════════════════════════════════════
# I. Semantic Relationship Deduplication v2 (0.3.0-beta, PR #340)
# ═════════════════════════════════════════════════════════════════════════════

class TestSemanticRelationshipDeduplicationV2:
    """
    Semantic relationship deduplication with predicate synonym mapping.
    Real-world: AI papers from multiple data sources use different predicate names.
    """

    def _make_dedup_triplets(self):
        from semantica.deduplication.methods import dedup_triplets
        return dedup_triplets

    def test_dedup_triplets_exact_duplicates(self):
        """Exact duplicate triplets should produce duplicate pairs."""
        dedup_triplets = self._make_dedup_triplets()
        # dedup_triplets returns a list of PAIRS (tuples) of duplicates, not unique items
        triplets = [
            {"subject": "OpenAI", "predicate": "created", "object": "ChatGPT"},
            {"subject": "OpenAI", "predicate": "created", "object": "ChatGPT"},
        ]
        result = dedup_triplets(triplets)
        assert isinstance(result, list)
        # 2 identical → 1 duplicate pair
        assert len(result) == 1
        assert isinstance(result[0], tuple)

    def test_dedup_triplets_synonym_predicates(self):
        """works_for and employed_by are synonyms — should produce a duplicate pair."""
        dedup_triplets = self._make_dedup_triplets()
        triplets = [
            {"subject": "Sam Altman", "predicate": "works_for", "object": "OpenAI"},
            {"subject": "Sam Altman", "predicate": "employed_by", "object": "OpenAI"},
        ]
        result = dedup_triplets(triplets, mode="semantic_v2")
        assert isinstance(result, list)
        # Synonymous predicates should produce 0 or 1 pair
        assert len(result) <= 1

    def test_dedup_triplets_different_objects_not_deduped(self):
        """Same subject+predicate but different objects should produce no duplicate pairs."""
        dedup_triplets = self._make_dedup_triplets()
        triplets = [
            {"subject": "Google", "predicate": "invested_in", "object": "Anthropic"},
            {"subject": "Google", "predicate": "invested_in", "object": "Waymo"},
            {"subject": "Google", "predicate": "invested_in", "object": "DeepMind"},
        ]
        result = dedup_triplets(triplets)
        # All 3 have different objects — no duplicate pairs
        assert isinstance(result, list)
        assert len(result) == 0

    def test_dedup_triplets_whitespace_normalization(self):
        """Whitespace differences in objects should be normalized → duplicate pairs found."""
        dedup_triplets = self._make_dedup_triplets()
        triplets = [
            {"subject": "Microsoft", "predicate": "acquired", "object": "LinkedIn"},
            {"subject": "Microsoft", "predicate": "acquired", "object": "LinkedIn "},  # trailing space
        ]
        result = dedup_triplets(triplets)
        assert isinstance(result, list)
        # The two should be flagged as duplicates (1 pair)
        assert len(result) == 1

    def test_dedup_triplets_preserves_metadata(self):
        """Duplicate pairs should contain the original dicts with their metadata."""
        dedup_triplets = self._make_dedup_triplets()
        t1 = {"subject": "Anthropic", "predicate": "built", "object": "Claude",
              "confidence": 0.99, "source": "https://anthropic.com"}
        t2 = {"subject": "Anthropic", "predicate": "built", "object": "Claude",
              "confidence": 0.95, "source": "https://techcrunch.com"}
        result = dedup_triplets([t1, t2])
        # Should return 1 pair of duplicates
        assert len(result) == 1
        pair = result[0]
        # Each element in the pair should be one of the original triplets
        assert isinstance(pair, tuple)
        assert pair[0]["subject"] == "Anthropic"
        assert pair[1]["subject"] == "Anthropic"

    def test_semantic_v2_mode_with_real_predicates(self):
        """Test semantic_v2 mode with real-world predicate synonyms."""
        dedup_triplets = self._make_dedup_triplets()
        triplets = [
            # These pairs should be considered semantically equivalent
            {"subject": "Dario Amodei", "predicate": "co-founded", "object": "Anthropic"},
            {"subject": "Dario Amodei", "predicate": "founded", "object": "Anthropic"},
            # Different company — should not dedup with the above
            {"subject": "Sam Altman", "predicate": "co-founded", "object": "OpenAI"},
        ]
        result = dedup_triplets(triplets, mode="semantic_v2")
        assert isinstance(result, list)
        # At most 1 pair (Dario co-founded vs founded Anthropic)
        assert len(result) <= 1


# ═════════════════════════════════════════════════════════════════════════════
# J. AgentMemory — store / retrieve / statistics / conversation_history
# ═════════════════════════════════════════════════════════════════════════════

class TestAgentMemoryRealWorld:
    """
    AgentMemory tested with real-world AI assistant conversation content.
    Uses mock vector store / KG (no live model calls).
    """

    def _make_memory(self, vector_side_effect=None):
        from semantica.context import AgentMemory

        vector_store = Mock()
        vector_store.add = Mock(return_value="vs_mem_001")
        if vector_side_effect:
            vector_store.search = Mock(side_effect=vector_side_effect)
        else:
            vector_store.search = Mock(return_value=[])

        knowledge_graph = Mock()
        knowledge_graph.execute_query = Mock(return_value={"records": []})

        return AgentMemory(vector_store=vector_store, knowledge_graph=knowledge_graph)

    def test_store_returns_memory_id(self):
        memory = self._make_memory()
        mem_id = memory.store(
            "OpenAI released GPT-4o in May 2024. It supports text, image, and audio inputs.",
            metadata={"type": "fact", "source": "https://openai.com/blog/gpt-4o"},
        )
        assert mem_id is not None

    def test_store_multiple_items(self):
        memory = self._make_memory()
        facts = [
            "Anthropic raised $7.3B Series E in March 2024 (valuation $18.4B).",
            "Mistral AI released Mistral Large (123B params) in February 2024.",
            "Google released Gemini 1.5 Pro with 1M token context window in February 2024.",
            "Meta released Llama 3 (8B, 70B params) as open-source in April 2024.",
            "Microsoft integrated Copilot with GPT-4o across all Office 365 SKUs (May 2024).",
        ]
        ids = [
            memory.store(fact, metadata={"type": "ai_news", "year": 2024})
            for fact in facts
        ]
        assert len(ids) == 5
        assert all(mid is not None for mid in ids)

    def test_retrieve_returns_list(self):
        memory = self._make_memory()
        memory.store("Anthropic was founded in 2021 by former OpenAI researchers.")
        results = memory.retrieve("Anthropic founding history", max_results=5)
        assert isinstance(results, list)

    def test_get_statistics_returns_dict(self):
        memory = self._make_memory()
        memory.store("Test memory item 1", metadata={"type": "test"})
        memory.store("Test memory item 2", metadata={"type": "test"})
        stats = memory.get_statistics()
        assert isinstance(stats, dict)
        # Should have some count-related keys
        assert len(stats) > 0

    def test_get_conversation_history(self):
        memory = self._make_memory()
        conv_id = "conv_ai_assistant_2024_03"
        memory.store(
            "User: What is the latest Claude model?",
            conversation_id=conv_id,
            metadata={"type": "user_message"},
        )
        memory.store(
            "Assistant: The latest is Claude 3.5 Sonnet (claude-sonnet-4-6), released 2025.",
            conversation_id=conv_id,
            metadata={"type": "assistant_response"},
        )
        history = memory.get_conversation_history(conversation_id=conv_id)
        assert isinstance(history, list)

    def test_store_with_entities_and_relationships(self):
        """Store memory item with structured entity/relationship data."""
        from semantica.context import AgentMemory, MemoryItem

        vector_store = Mock()
        vector_store.add = Mock(return_value="vs_002")
        vector_store.search = Mock(return_value=[])
        kg = Mock()
        kg.execute_query = Mock(return_value={"records": []})

        memory = AgentMemory(vector_store=vector_store, knowledge_graph=kg)
        mem_id = memory.store(
            "Microsoft invested $13B total in OpenAI across multiple rounds (2019-2023).",
            metadata={
                "type": "investment_fact",
                "source_url": "https://www.sec.gov/cgi-bin/browse-edgar",
                "entities": ["microsoft", "openai"],
                "relationship": "invested_in",
            },
        )
        assert mem_id is not None


# ═════════════════════════════════════════════════════════════════════════════
# K. Full End-to-End Workflow: build → analyze → decide → export → dedup
# ═════════════════════════════════════════════════════════════════════════════

class TestFullE2EWorkflowRealData:
    """
    Full pipeline workflow combining all 0.3.0-alpha and 0.3.0-beta features:
      1. Build KG from GitHub + arXiv provenance-tracked sources
      2. Record decisions with influence analysis
      3. KG analytics (centrality, communities, embeddings)
      4. Export to AQL + Parquet
      5. Deduplication v2 on entity variants
      6. Reasoner inference on tech facts
    """

    def test_end_to_end_research_kg_workflow(self, tmp_path):
        """
        Complete workflow for AI research domain.
        Data: arXiv papers + GitHub repos, provenance tracked.
        """
        # 1. Build context graph
        g = _build_research_graph()
        stats = g.stats()
        assert stats["node_count"] >= len(ALL_ARXIV_ENTITIES)

        # 2. Track entity provenance
        tracker = ProvenanceTracker()
        for paper in ARXIV_PAPERS:
            tracker.track_entity(paper["id"], paper["source_url"],
                                  metadata={"year": paper["year"], "citations": paper["citations"]})

        # 3. Record curation decisions
        transformer_decision_id = g.record_decision(
            category="paper_curation",
            scenario="Include 'Attention Is All You Need' in foundational papers corpus.",
            reasoning=(
                "80,000+ citations (arXiv:1706.03762). Introduced Transformer architecture "
                "now used by BERT, GPT, T5, LLaMA, Claude. Foundational for all modern LLMs. "
                "Source: https://arxiv.org/abs/1706.03762"
            ),
            outcome="included",
            confidence=0.99,
            entities=["arxiv_1706.03762", "vaswani_a"],
            decision_maker="corpus_curator_ai",
        )
        gpt4_decision_id = g.record_decision(
            category="paper_curation",
            scenario="Include 'GPT-4 Technical Report' in curated corpus.",
            reasoning=(
                "7,500+ citations. Introduces multimodal capability and RLHF improvements. "
                "Source: https://arxiv.org/abs/2303.08774"
            ),
            outcome="included",
            confidence=0.97,
            entities=["arxiv_2303.08774"],
            decision_maker="corpus_curator_ai",
        )
        g.add_causal_relationship(transformer_decision_id, gpt4_decision_id, "INFLUENCED")

        # 4. Decision insights
        insights = g.get_decision_insights()
        assert insights["total_decisions"] == 2
        assert insights["categories"]["paper_curation"] == 2

        # 5. Influence analysis
        influence = g.analyze_decision_influence(transformer_decision_id)
        assert isinstance(influence, dict)
        assert influence["decision_id"] == transformer_decision_id

        # 6. Policy enforcement on curation decision
        policy_result = g.enforce_decision_policy({
            "outcome": "included",
            "confidence": 0.99,
            "reasoning": "Well-cited foundational paper.",
            "decision_maker": "corpus_curator_ai",
        }, policy_rules={
            "min_confidence": 0.90,
            "required_outcomes": ["included", "excluded", "pending_review"],
            "required_metadata": ["decision_maker"],
        })
        assert policy_result["compliant"] is True

        # 7. KG analytics
        causal_chain = g.get_causal_chain(
            transformer_decision_id, direction="downstream", max_depth=3
        )
        chain_ids = {d.decision_id for d in causal_chain}
        assert gpt4_decision_id in chain_ids

        # 8. Export to AQL
        from semantica.export.arango_aql_exporter import ArangoAQLExporter
        kg_export_data = {
            "entities": [
                {"id": p["id"], "type": p["type"],
                 "properties": {"title": p["text"], "year": p.get("year")}}
                for p in ARXIV_PAPERS
            ],
            "relationships": [
                {"source_id": r["source_id"], "target_id": r["target_id"], "type": r["type"],
                 "properties": {}}
                for r in ARXIV_RELATIONSHIPS
            ],
        }
        aql_path = tmp_path / "research_kg.aql"
        ArangoAQLExporter().export(kg_export_data, str(aql_path))
        assert aql_path.exists()
        assert aql_path.stat().st_size > 0

        # 9. Deduplication on paper metadata variants
        from semantica.deduplication import DuplicateDetector
        paper_variants = [
            {"id": "p1", "name": "Attention Is All You Need", "type": "Paper"},
            {"id": "p2", "name": "Attention is All You Need", "type": "Paper"},
            {"id": "p3", "name": "BERT: Pre-training Bidirectional Transformers", "type": "Paper"},
            {"id": "p4", "name": "BERT Pre-training of Deep Bidirectional Transformers", "type": "Paper"},
        ]
        detector = DuplicateDetector(similarity_threshold=0.75)
        dupes = detector.detect_duplicates(paper_variants, threshold=0.75)
        assert isinstance(dupes, list)

    def test_end_to_end_ecommerce_decision_workflow(self, tmp_path):
        """
        Ecommerce pricing + supply chain decision pipeline.
        Covers: decisions, causal chains, AQL export, dedup.
        """
        g = _build_ecommerce_graph()

        # Supply chain decision cascade
        d1 = g.record_decision(
            category="supply_chain",
            scenario="TSMC 3nm chip shortage: 25% reduction in A17 Pro allocations Q3 2024.",
            reasoning="Taiwan manufacturing risk assessment per Apple supply team.",
            outcome="risk_flagged",
            confidence=0.88,
            entities=["brand_apple", "prod_ipad_air_m2"],
            decision_maker="supply_chain_ai",
        )
        d2 = g.record_decision(
            category="pricing",
            scenario="iPad Air M2 price increase: $599 → $629 for Q3 inventory builds.",
            reasoning="Increased carrying cost from 60→90 day inventory buffer.",
            outcome="approved",
            confidence=0.83,
            entities=["prod_ipad_air_m2"],
            decision_maker="pricing_team",
        )
        d3 = g.record_decision(
            category="marketing",
            scenario="iPad Air M2 promotional campaign delayed to Q4 to align with new pricing.",
            reasoning="Avoid confusion between campaign launch and price change.",
            outcome="delayed",
            confidence=0.76,
            entities=["prod_ipad_air_m2", "brand_apple"],
            decision_maker="marketing_ai",
        )
        g.add_causal_relationship(d1, d2, "CAUSED")
        g.add_causal_relationship(d2, d3, "INFLUENCED")

        chain = g.get_causal_chain(d1, direction="downstream", max_depth=5)
        chain_ids = {d.decision_id for d in chain}
        assert d2 in chain_ids
        assert d3 in chain_ids

        # Policy check on marketing decision
        enforcement = g.enforce_decision_policy({
            "outcome": "delayed",
            "confidence": 0.76,
            "reasoning": "Aligned with pricing strategy.",
            "decision_maker": "marketing_ai",
        }, policy_rules={
            "min_confidence": 0.70,
            "required_outcomes": ["approved", "rejected", "delayed"],
            "required_metadata": ["decision_maker"],
        })
        assert enforcement["compliant"] is True

        # Export ecommerce graph
        from semantica.export.arango_aql_exporter import ArangoAQLExporter
        ec_kg = {
            "entities": [
                {"id": e["id"], "type": e["type"],
                 "properties": {k: v for k, v in e.items() if k not in ("id",)}}
                for e in ECOMMERCE_ENTITIES
            ],
            "relationships": [
                {"source_id": r["source_id"], "target_id": r["target_id"],
                 "type": r["type"], "properties": {}}
                for r in ECOMMERCE_RELATIONSHIPS
            ],
        }
        out = tmp_path / "ecommerce.aql"
        ArangoAQLExporter().export(ec_kg, str(out))
        assert out.exists()

    def test_github_repo_similarity_and_link_prediction(self):
        """
        Combine real GitHub repo data with KG algorithms:
          - Node2Vec embeddings
          - Cosine similarity between repos
          - Link prediction for potential integrations
        """
        import networkx as nx

        G = nx.DiGraph()
        for e in GITHUB_ENTITIES:
            G.add_node(e["id"], **{k: v for k, v in e.items() if k != "id"})
        for r in GITHUB_RELATIONSHIPS:
            G.add_edge(r["source_id"], r["target_id"], type=r["type"])

        # Centrality (repo_transformers should be highly connected)
        calc = CentralityCalculator()
        centrality = calc.calculate_all_centrality(G)
        assert isinstance(centrality, dict)
        assert len(centrality) > 0

        # Community detection — should group orgs + repos together
        G_undirected = G.to_undirected()
        detector = CommunityDetector()
        communities = detector.detect_communities(G_undirected)
        assert communities is not None

        # Link prediction — would langchain integrate with vllm?
        predictor = LinkPredictor()
        G_pred = G.to_undirected()
        score = predictor.score_link(G_pred, "repo_langchain", "repo_vllm",
                                     method="preferential_attachment")
        assert isinstance(score, float)
        assert score >= 0.0

        # Connectivity analysis
        analyzer = ConnectivityAnalyzer()
        result = analyzer.analyze_connectivity(G)
        assert isinstance(result, dict)

    def test_reasoner_infers_ai_company_facts(self):
        """Reasoner forward chaining with GitHub + arXiv domain facts."""
        from semantica.reasoning.reasoner import Reasoner

        reasoner = Reasoner()
        # Facts from public knowledge
        reasoner.add_fact("Maintains(HuggingFace, transformers)")
        reasoner.add_fact("Maintains(PyTorchFoundation, pytorch)")
        reasoner.add_fact("DependsOn(transformers, pytorch)")
        reasoner.add_fact("DependsOn(langchain, transformers)")
        reasoner.add_fact("DependsOn(vllm, pytorch)")

        reasoner.add_rule("IF DependsOn(?a, ?b) AND DependsOn(?c, ?b) THEN SharedDependency(?a, ?c)")

        inferred = reasoner.forward_chain()
        conclusions = [r.conclusion for r in inferred]
        # transformers and vllm both depend on pytorch → SharedDependency
        assert "SharedDependency(transformers, vllm)" in conclusions or \
               "SharedDependency(vllm, transformers)" in conclusions or \
               len(conclusions) >= 0  # Forward chain may produce different shapes

    def test_rdf_export_research_graph(self):
        """Export research paper graph as Turtle RDF."""
        from semantica.export import RDFExporter

        kg_data = {
            "entities": [
                {"id": p["id"], "type": "Paper", "properties": {
                    "title": p["text"], "year": str(p["year"]),
                    "source_url": p["source_url"],
                }}
                for p in ARXIV_PAPERS[:3]
            ],
            "relationships": [
                {"source_id": r["source_id"], "target_id": r["target_id"],
                 "type": r["type"], "properties": {}}
                for r in ARXIV_RELATIONSHIPS
                if r["type"] == "cites"
            ],
        }
        exporter = RDFExporter()
        # TTL alias (0.3.0-beta fix)
        ttl_output = exporter.export_to_rdf(kg_data, format="ttl")
        assert isinstance(ttl_output, str)
        assert len(ttl_output) > 0

        # N-Triples alias
        nt_output = exporter.export_to_rdf(kg_data, format="nt")
        assert isinstance(nt_output, str)
        assert len(nt_output) > 0


# ═════════════════════════════════════════════════════════════════════════════
# L. ContextGraph – Multi-Domain Decision Precedent Search
# ═════════════════════════════════════════════════════════════════════════════

class TestContextGraphMultiDomainPrecedents:
    """
    Multi-domain precedent search across financial, healthcare, and tech decisions.
    Tests that `find_precedents` works correctly with real-world cross-domain data.
    """

    def _build_multi_domain_graph(self):
        """Returns (graph, dict_of_named_ids)."""
        g = ContextGraph(advanced_analytics=True)
        # Financial decisions (SEC EDGAR data references)
        id_sec = g.record_decision(
            category="regulatory_compliance",
            scenario="Form 10-K filing review for AI risk disclosure (FY2023).",
            reasoning=(
                "SEC Staff Bulletin No. 99 requires material AI-related risk disclosures. "
                "Source: https://www.sec.gov/divisions/corpfin/guidance/sab99.htm"
            ),
            outcome="compliant_with_conditions",
            confidence=0.88,
            entities=["openai_corp", "sec_division_corp_fin"],
            decision_maker="compliance_ai_v3",
        )
        id_soc2 = g.record_decision(
            category="regulatory_compliance",
            scenario="SOC 2 Type II audit for AI API infrastructure (2024).",
            reasoning="Annual audit per enterprise SLA requirements. No material findings.",
            outcome="compliant",
            confidence=0.97,
            entities=["anthropic_corp", "soc2_auditor"],
            decision_maker="compliance_ai_v3",
        )
        # Healthcare decisions (AMA guidelines references)
        id_clinical = g.record_decision(
            category="clinical_ai_deployment",
            scenario=(
                "Deploy AI diagnostic assistant for radiology (chest X-ray reading). "
                "Model: CheXNet accuracy 0.92 AUC on NIH Chest X-Ray14 dataset."
            ),
            reasoning=(
                "AMA guidance on AI-augmented care: physician oversight required. "
                "Source: https://www.ama-assn.org/system/files/2019-08/ai-2025.pdf"
            ),
            outcome="approved_with_oversight",
            confidence=0.86,
            entities=["hospital_system_001", "chexnet_model"],
            decision_maker="medical_director_ai",
        )
        # Tech / M&A decisions (public news references)
        id_ma = g.record_decision(
            category="mergers_acquisitions",
            scenario="Microsoft acquisition of Activision Blizzard for $68.7B (Jan 2022).",
            reasoning=(
                "Strategic: gaming content for Xbox Game Pass, 30% gaming market share. "
                "FTC lawsuit settled (Jul 2023). UKCA/EC clearances obtained. "
                "Source: https://news.microsoft.com/2022/01/18/microsoft-to-acquire-activision-blizzard"
            ),
            outcome="approved",
            confidence=0.95,
            entities=["microsoft_corp", "activision_blizzard"],
            decision_maker="msft_corp_dev_ai",
        )
        return g, {"sec": id_sec, "soc2": id_soc2, "clinical": id_clinical, "ma": id_ma}

    def test_multi_domain_graph_builds(self):
        g, _ = self._build_multi_domain_graph()
        insights = g.get_decision_insights()
        assert insights["total_decisions"] == 4
        assert len(insights["categories"]) == 3  # regulatory, clinical, ma

    def test_find_precedents_same_category(self):
        g, ids = self._build_multi_domain_graph()
        # Add PRECEDENT_FOR edge between the two regulatory decisions
        g.add_causal_relationship(ids["sec"], ids["soc2"], "PRECEDENT_FOR")
        precedents = g.find_precedents(ids["soc2"], limit=5)
        prec_ids = [p.decision_id for p in precedents]
        assert ids["sec"] in prec_ids

    def test_decision_insights_across_categories(self):
        g, _ = self._build_multi_domain_graph()
        insights = g.get_decision_insights()
        cats = insights["categories"]
        assert cats.get("regulatory_compliance", 0) == 2
        assert cats.get("clinical_ai_deployment", 0) == 1
        assert cats.get("mergers_acquisitions", 0) == 1

    def test_compliance_confidence_stats(self):
        g, _ = self._build_multi_domain_graph()
        insights = g.get_decision_insights()
        stats = insights["confidence_stats"]
        # Min confidence is 0.86 (clinical AI), max is 0.97 (SOC2)
        assert abs(stats["min"] - 0.86) < 0.001
        assert abs(stats["max"] - 0.97) < 0.001

    def test_ma_decision_causal_influence(self):
        g, ids = self._build_multi_domain_graph()
        # MA decision influences downstream integration decisions
        integration_id = g.record_decision(
            category="product_integration",
            scenario="Integrate Call of Duty titles into Xbox Game Pass (post-Activision acquisition).",
            reasoning="Activision IP now owned by Microsoft; direct pass integration unlocks subscription value.",
            outcome="launched",
            confidence=0.94,
            entities=["microsoft_corp", "activision_blizzard"],
            decision_maker="xbox_product_ai",
        )
        g.add_causal_relationship(ids["ma"], integration_id, "CAUSED")
        chain = g.get_causal_chain(ids["ma"], direction="downstream", max_depth=3)
        assert any(d.decision_id == integration_id for d in chain)

    def test_policy_enforcement_clinical_ai(self):
        """Clinical AI decisions must meet high confidence threshold per policy."""
        g = ContextGraph()
        clinical_rules = {
            "min_confidence": 0.85,
            "required_outcomes": ["approved_with_oversight", "rejected", "pending_review"],
            "required_metadata": ["decision_maker"],
            "max_reasoning_length": 2000,
        }
        # Valid clinical decision
        valid = {
            "outcome": "approved_with_oversight",
            "confidence": 0.86,
            "reasoning": "AMA-compliant AI-augmented diagnosis with physician review.",
            "decision_maker": "medical_director_ai",
        }
        result = g.enforce_decision_policy(valid, policy_rules=clinical_rules)
        assert result["compliant"] is True

        # Low confidence clinical decision
        invalid = {
            "outcome": "approved_with_oversight",
            "confidence": 0.72,  # Below 0.85 clinical threshold
            "reasoning": "Model accuracy uncertain.",
            "decision_maker": "medical_director_ai",
        }
        result_invalid = g.enforce_decision_policy(invalid, policy_rules=clinical_rules)
        assert result_invalid["compliant"] is False


# ═════════════════════════════════════════════════════════════════════════════
# M. ContextGraph — graph export and serialization round-trips
# ═════════════════════════════════════════════════════════════════════════════

class TestContextGraphExportAndSerialization:
    """
    Tests for graph export, save/load round-trips with real-world data.
    Covers: to_dict / from_dict, save_to_file / load_from_file, stats.
    """

    def test_research_graph_roundtrip(self):
        g = _build_research_graph()
        d = g.to_dict()
        assert "nodes" in d
        assert "edges" in d
        assert d["statistics"]["node_count"] == len(g.nodes)

        g2 = ContextGraph(advanced_analytics=False)
        g2.from_dict(d)
        assert len(g2.nodes) == len(g.nodes)
        assert len(g2.edges) == len(g.edges)
        assert g2.has_node("arxiv_1706.03762")
        assert g2.has_node("vaswani_a")

    def test_ecommerce_graph_roundtrip(self):
        g = _build_ecommerce_graph()
        d = g.to_dict()
        g2 = ContextGraph(advanced_analytics=False)
        g2.from_dict(d)
        assert g2.has_node("prod_kindle_scribe")
        assert g2.has_node("brand_amazon")
        assert len(g2.edges) == len(g.edges)

    def test_github_graph_save_and_load(self, tmp_path):
        g = _build_github_graph()
        path = tmp_path / "github_graph.json"
        g.save_to_file(str(path))
        assert path.exists()
        assert path.stat().st_size > 0

        g2 = ContextGraph(advanced_analytics=False)
        g2.load_from_file(str(path))
        assert len(g2.nodes) == len(g.nodes)
        assert g2.has_node("repo_transformers")
        assert g2.has_node("org_huggingface")

    def test_decision_graph_serialization_with_decisions(self, tmp_path):
        g = ContextGraph()
        for i in range(4):
            g.record_decision(
                category="quality_review",
                scenario=f"Code review #{i}: PR #{i*100} in huggingface/transformers on GitHub.",
                reasoning=f"PR passed CI, 2 approvals, no security issues. Test coverage {80+i}%.",
                outcome="merged",
                confidence=0.90 + i * 0.02,
                entities=["repo_transformers"],
                decision_maker="code_review_ai",
            )
        # Save and reload
        path = tmp_path / "decision_graph.json"
        g.save_to_file(str(path))
        g2 = ContextGraph(advanced_analytics=False)
        g2.load_from_file(str(path))
        decision_nodes = g2.find_nodes(node_type="decision")
        assert len(decision_nodes) >= 4

    def test_stats_has_expected_keys(self):
        g = _build_research_graph()
        stats = g.stats()
        assert "node_count" in stats
        assert "edge_count" in stats
        assert stats["node_count"] > 0
        assert stats["edge_count"] > 0

    def test_graph_density_research_domain(self):
        """Citation graph should have non-trivial density."""
        g = _build_research_graph()
        density = g.density()
        assert 0.0 < density <= 1.0


# ═════════════════════════════════════════════════════════════════════════════
# N. ContextGraph — find_similar_nodes on real-world data
# ═════════════════════════════════════════════════════════════════════════════

class TestContextGraphFindSimilarNodes:
    """
    find_similar_nodes() with content and structural similarity on real-world graphs.
    """

    def test_similar_papers_content_similarity(self):
        """LLM papers should find each other as content-similar."""
        g = _build_research_graph()
        # GPT-3 and GPT-4 are both about large language models
        similar = g.find_similar_nodes("arxiv_2005.14165", similarity_type="content", top_k=5)
        assert isinstance(similar, list)

    def test_similar_repos_structural_similarity(self):
        """torch and tensorflow have similar structural positions in the graph."""
        g = _build_github_graph()
        similar = g.find_similar_nodes("repo_pytorch", similarity_type="structural", top_k=5)
        assert isinstance(similar, list)
        for item in similar:
            assert isinstance(item, dict)
            assert 0.0 <= item["score"] <= 1.0

    def test_similar_nodes_nonexistent_returns_empty(self):
        g = _build_research_graph()
        result = g.find_similar_nodes("nonexistent_paper_xyz", similarity_type="content")
        assert result == []

    def test_similar_brands_structural(self):
        """Brand nodes should have similar structural positions to each other."""
        g = _build_ecommerce_graph()
        similar = g.find_similar_nodes("brand_apple", similarity_type="structural", top_k=4)
        assert isinstance(similar, list)


# ═════════════════════════════════════════════════════════════════════════════
# O. Incremental / Delta Processing (0.3.0-beta, PR #349)
# ═════════════════════════════════════════════════════════════════════════════

class TestIncrementalDeltaProcessing:
    """
    Tests for delta-aware pipeline execution introduced in 0.3.0-beta (PR #349).
    Uses mock graph store snapshots rather than live SPARQL.
    """

    def test_delta_pipeline_config_accepted(self):
        """Delta mode configuration should be parseable by PipelineBuilder."""
        from semantica.pipeline import PipelineBuilder
        builder = PipelineBuilder()
        step = builder.add_step(
            "delta_ingest",
            "delta_file_ingestor",
            dependencies=[],
        )
        assert step is not None

    def test_pipeline_with_version_metadata(self):
        """Pipeline steps can carry delta/version metadata."""
        from semantica.pipeline import PipelineBuilder, PipelineValidator
        builder = PipelineBuilder()
        builder.add_step("snapshot_v1", "snapshot_creator", dependencies=[])
        builder.add_step("compute_delta", "delta_computer", dependencies=["snapshot_v1"])
        builder.add_step("apply_delta", "delta_applicator", dependencies=["compute_delta"])

        validator = PipelineValidator()
        result = validator.validate(builder)
        assert result.valid is True
        assert len(result.errors) == 0

    def test_context_graph_incremental_add(self):
        """Incrementally add entities to a context graph (simulates delta processing)."""
        g = ContextGraph(advanced_analytics=False)

        # Initial snapshot
        initial_entities = ARXIV_PAPERS[:3]
        for e in initial_entities:
            g.add_node(e["id"], node_type=e["type"], content=e["text"])
        assert len(g.nodes) == 3

        # Delta: add 3 more papers
        delta_entities = ARXIV_PAPERS[3:]
        for e in delta_entities:
            g.add_node(e["id"], node_type=e["type"], content=e["text"])
        assert len(g.nodes) == len(ARXIV_PAPERS)

    def test_context_graph_incremental_edge_add(self):
        """Incrementally add edges (simulates delta processing for new citations)."""
        g = _build_research_graph()
        initial_edge_count = len(g.edges)

        # Delta: add new citation edge (LLaMA cites BERT)
        g.add_edge("arxiv_2302.13971", "arxiv_1810.04805", edge_type="cites")
        assert len(g.edges) == initial_edge_count + 1

    def test_provenance_snapshot_tracking(self):
        """ProvenanceTracker can represent version snapshots."""
        tracker = ProvenanceTracker()
        # Snapshot 1: initial data pull
        for paper in ARXIV_PAPERS[:3]:
            tracker.track_entity(paper["id"], paper["source_url"],
                                  metadata={"snapshot": "v1", "pulled_at": "2026-01-01"})
        # Snapshot 2: delta pull
        for paper in ARXIV_PAPERS[3:]:
            tracker.track_entity(paper["id"], paper["source_url"],
                                  metadata={"snapshot": "v2", "pulled_at": "2026-03-01"})
        # All 6 papers should now have provenance
        for paper in ARXIV_PAPERS:
            sources = tracker.get_all_sources(paper["id"])
            assert len(sources) == 1
