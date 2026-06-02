"""
Shared fixtures and threshold constants for the Decision Intelligence benchmark suite.

Tracks 1.1, 1.2, 1.3, 1.4, 30, 31.

Dataset fixtures skip automatically when the corresponding dataset path is
absent from disk.  Fixture-backed tests (influence ground-truth, compliance
synthetic data) always run.
"""

import json
import pathlib
import time
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import pytest

# ---------------------------------------------------------------------------
# Threshold constants
# ---------------------------------------------------------------------------

THRESHOLD_MRR_GERMAN_CREDIT = 0.70
THRESHOLD_NDCG10_CUAD = 0.65
THRESHOLD_GRAPH_LIFT = 0.05
THRESHOLD_P95_10K_MS = 100
THRESHOLD_P95_100K_MS = 500

THRESHOLD_DIRECTION_ACCURACY = 0.72
THRESHOLD_ATOMIC_RECALL = 0.80
THRESHOLD_ATOMIC_PRECISION = 0.85
THRESHOLD_INTERVENTION_ACCURACY = 0.60
THRESHOLD_CHAIN_P95_MS = 500

THRESHOLD_INFLUENCE_RECALL_3 = 0.85
THRESHOLD_INFLUENCE_RECALL_5 = 0.75
THRESHOLD_SPURIOUS_RATE = 0.10

THRESHOLD_COMPLIANCE_ACCURACY = 0.88
THRESHOLD_FALSE_NEGATIVE_RATE = 0.05  # HARD GATE
THRESHOLD_CLAUSE_F1 = 0.75

# ---------------------------------------------------------------------------
# Dataset path helpers
# ---------------------------------------------------------------------------

_BENCHMARKS_ROOT = pathlib.Path(__file__).resolve().parents[1]
_DATASETS_ROOT = _BENCHMARKS_ROOT / "datasets" / "decision_intelligence"
_FIXTURES_ROOT = _BENCHMARKS_ROOT / "fixtures"


def _dataset_path(name: str) -> pathlib.Path:
    return _DATASETS_ROOT / name


def _fixture_path(rel: str) -> pathlib.Path:
    return _FIXTURES_ROOT / rel


# ---------------------------------------------------------------------------
# Helpers — dataset loaders
# ---------------------------------------------------------------------------


def load_german_credit(path: pathlib.Path) -> List[Dict[str, Any]]:
    """Load German Credit dataset (UCI statlog format, space-separated)."""
    records = []
    data_file = path / "german.data"
    with data_file.open() as fh:
        for idx, line in enumerate(fh):
            parts = line.strip().split()
            if len(parts) < 21:
                continue
            records.append(
                {
                    "id": f"gc_{idx:04d}",
                    "status": parts[0],
                    "duration": int(parts[1]),
                    "credit_history": parts[2],
                    "purpose": parts[3],
                    "credit_amount": int(parts[4]),
                    "savings": parts[5],
                    "employment": parts[6],
                    "installment_rate": int(parts[7]),
                    "personal_status": parts[8],
                    "debtors": parts[9],
                    "residence_duration": int(parts[10]),
                    "property": parts[11],
                    "age": int(parts[12]),
                    "installment_plans": parts[13],
                    "housing": parts[14],
                    "existing_credits": int(parts[15]),
                    "job": parts[16],
                    "dependents": int(parts[17]),
                    "telephone": parts[18],
                    "foreign_worker": parts[19],
                    "label": int(parts[20]),  # 1=good, 2=bad
                }
            )
    return records


def load_cuad(path: pathlib.Path) -> Dict[str, Any]:
    """Load CUAD dataset (JSON format from HuggingFace)."""
    candidates = list(path.glob("*.json"))
    if not candidates:
        raise FileNotFoundError(f"No JSON file found in {path}")
    raw = json.loads(candidates[0].read_text(encoding="utf-8"))
    # Handle both SQuAD-format and HuggingFace dict format
    if "data" in raw:
        return raw
    return {"data": raw.get("train", raw)}


def load_ledgar(path: pathlib.Path) -> List[Dict[str, Any]]:
    """Load LEDGAR dataset (JSONL format)."""
    records = []
    candidates = list(path.glob("*.json")) + list(path.glob("*.jsonl"))
    if not candidates:
        raise FileNotFoundError(f"No JSON/JSONL in {path}")
    src = candidates[0]
    with src.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    if not records:
        raw = json.loads(src.read_text(encoding="utf-8"))
        if isinstance(raw, list):
            records = raw
        elif isinstance(raw, dict):
            for k in ("text", "label", "provisions"):
                if k in raw and isinstance(raw[k], list):
                    records = [
                        {"text": t, "label": l}
                        for t, l in zip(raw.get("text", []), raw.get("label", []))
                    ]
                    break
    return records


def load_atomic_subset(path: pathlib.Path) -> List[Dict[str, Any]]:
    """Load the 500-pair ATOMIC 2020 subset."""
    candidates = list(path.glob("*.json"))
    if not candidates:
        raise FileNotFoundError(f"No JSON in {path}")
    return json.loads(candidates[0].read_text(encoding="utf-8"))


def load_ecare(path: pathlib.Path) -> List[Dict[str, Any]]:
    """Load e-CARE dataset (JSONL)."""
    records = []
    for fname in ["train.jsonl", "dev.jsonl"]:
        fpath = path / fname
        if fpath.exists():
            with fpath.open(encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if line:
                        records.append(json.loads(line))
    return records


def load_causalbench(path: pathlib.Path) -> Dict[str, Any]:
    """Load CausalBench direction and intervention splits."""
    result: Dict[str, Any] = {}
    for key, fname in [("direction", "direction_test.json"), ("intervention", "intervention_test.json")]:
        fpath = path / fname
        if fpath.exists():
            result[key] = json.loads(fpath.read_text(encoding="utf-8"))
    return result


def load_trec_ct(path: pathlib.Path) -> Dict[str, Any]:
    """Load TREC CT 2022 topics and qrels."""
    result: Dict[str, Any] = {}
    qrels_path = path / "qrels2022.txt"
    topics_path = path / "topics2022.xml"
    if qrels_path.exists():
        qrels: Dict[str, Dict[str, int]] = defaultdict(dict)
        with qrels_path.open() as fh:
            for line in fh:
                parts = line.strip().split()
                if len(parts) >= 4:
                    topic_id, _, doc_id, rel = parts[:4]
                    qrels[topic_id][doc_id] = int(rel)
        result["qrels"] = dict(qrels)
    if topics_path.exists():
        result["topics_path"] = str(topics_path)
    return result


# ---------------------------------------------------------------------------
# Session-scoped real-dataset fixtures (skip when dataset absent)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def german_credit_dataset():
    p = _dataset_path("german_credit")
    if not (p / "german.data").exists():
        pytest.skip(f"German Credit dataset not found at {p}. Download per benchmarks/datasets/decision_intelligence/README.md")
    return load_german_credit(p)


@pytest.fixture(scope="session")
def cuad_dataset():
    p = _dataset_path("cuad")
    if not p.exists() or not list(p.glob("*.json")):
        pytest.skip(f"CUAD dataset not found at {p}. Download per benchmarks/datasets/decision_intelligence/README.md")
    return load_cuad(p)


@pytest.fixture(scope="session")
def ledgar_dataset():
    p = _dataset_path("ledgar")
    if not p.exists() or not (list(p.glob("*.json")) + list(p.glob("*.jsonl"))):
        pytest.skip(f"LEDGAR dataset not found at {p}. Download per benchmarks/datasets/decision_intelligence/README.md")
    return load_ledgar(p)


@pytest.fixture(scope="session")
def atomic_subset():
    p = _dataset_path("atomic_subset")
    if not p.exists() or not list(p.glob("*.json")):
        pytest.skip(f"ATOMIC 2020 subset not found at {p}. Download per benchmarks/datasets/decision_intelligence/README.md")
    return load_atomic_subset(p)


@pytest.fixture(scope="session")
def ecare_dataset():
    p = _dataset_path("ecare")
    if not p.exists() or not list(p.glob("*.jsonl")):
        pytest.skip(f"e-CARE dataset not found at {p}. Download per benchmarks/datasets/decision_intelligence/README.md")
    return load_ecare(p)


@pytest.fixture(scope="session")
def causalbench_dataset():
    p = _dataset_path("causalbench")
    if not p.exists():
        pytest.skip(f"CausalBench not found at {p}. Download per benchmarks/datasets/decision_intelligence/README.md")
    data = load_causalbench(p)
    if not data:
        pytest.skip(f"CausalBench files missing in {p}. Expected direction_test.json / intervention_test.json")
    return data


@pytest.fixture(scope="session")
def trec_ct_dataset():
    p = _dataset_path("trec_ct_2022")
    if not p.exists() or not (p / "qrels2022.txt").exists():
        pytest.skip(f"TREC CT 2022 not found at {p}. Download per benchmarks/datasets/decision_intelligence/README.md")
    return load_trec_ct(p)


# ---------------------------------------------------------------------------
# Session-scoped API fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def context_graph():
    """Bare ContextGraph used for general-purpose API tests."""
    from semantica.context.context_graph import ContextGraph
    return ContextGraph()


@pytest.fixture(scope="session")
def causal_chain_analyzer(context_graph):
    """CausalChainAnalyzer backed by the shared ContextGraph."""
    from semantica.context.causal_analyzer import CausalChainAnalyzer
    return CausalChainAnalyzer(graph_store=context_graph)


@pytest.fixture(scope="session")
def context_retriever(context_graph):
    """ContextRetriever backed by the shared ContextGraph."""
    from semantica.context.context_retriever import ContextRetriever
    return ContextRetriever(graph_store=context_graph)


@pytest.fixture(scope="session")
def decision_query(context_graph):
    """DecisionQuery backed by the shared ContextGraph."""
    from semantica.context.decision_query import DecisionQuery
    return DecisionQuery(graph_store=context_graph)


# ---------------------------------------------------------------------------
# Influence ground-truth fixture (Tracks 1.3 + 30)
# ---------------------------------------------------------------------------


def _bulk_load_influence_decisions(
    fixture_decisions: List[Dict[str, Any]],
) -> Tuple[Any, Dict[str, str]]:
    """
    Create a ContextGraph and load all fixture decisions via record_decision().

    Returns
    -------
    (graph, logical_id_to_uuid)
        graph               — populated ContextGraph
        logical_id_to_uuid  — maps fixture logical_id to the UUID that
                              record_decision() assigned to each decision
    """
    from semantica.context.context_graph import ContextGraph

    graph = ContextGraph()
    logical_id_to_uuid: Dict[str, str] = {}

    for d in fixture_decisions:
        uuid = graph.record_decision(
            category=d["category"],
            scenario=d["scenario"],
            reasoning=d["reasoning"],
            outcome=d["outcome"],
            confidence=d["confidence"],
            entities=d["entities"],
            decision_maker=d["decision_maker"],
        )
        logical_id_to_uuid[d["logical_id"]] = uuid

    return graph, logical_id_to_uuid


@pytest.fixture(scope="session")
def influence_ground_truth() -> Dict[str, Any]:
    """Load the committed influence ground-truth fixture."""
    fp = _fixture_path("decision_influence_ground_truth.json")
    if not fp.exists():
        pytest.skip(
            f"Influence ground-truth fixture not found at {fp}. "
            "Run: python benchmarks/scripts/generate_decision_influence_gt.py"
        )
    return json.loads(fp.read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def influence_graph_with_map(influence_ground_truth) -> Tuple[Any, Dict[str, str], Dict[str, Any]]:
    """
    Returns (graph, logical_id_to_uuid, fixture_data).

    The graph has all 500 decisions loaded; logical_id_to_uuid maps each
    fixture logical_id to the UUID that ContextGraph assigned.
    """
    graph, id_map = _bulk_load_influence_decisions(influence_ground_truth["decisions"])
    return graph, id_map, influence_ground_truth


# ---------------------------------------------------------------------------
# Synthetic compliance fixtures (Track 1.4 hard gate + Track 31) — always run
# ---------------------------------------------------------------------------


def _make_compliance_engine():
    """
    Returns (policy_engine, policy_id, records) where records is a list of
    {"decision": Decision, "is_compliant": bool}.

    Policy rules:
        allowed_outcomes: ["approved", "conditional"]
        min_confidence:   0.70

    Compliant decisions  (80): confidence >= 0.70, outcome in allowed set
    Non-compliant (20):
        - 10 with outcome="denied"  (outcome violation)
        - 10 with confidence=0.50   (confidence violation)
    """
    from semantica.context.context_graph import ContextGraph
    from semantica.context.decision_models import Decision, Policy
    from semantica.context.policy_engine import PolicyEngine

    graph = ContextGraph()
    engine = PolicyEngine(graph_store=graph)

    policy = Policy(
        policy_id="compliance_test_policy",
        name="Compliance Test Policy",
        description="Synthetic policy for FNR hard-gate benchmark",
        rules={
            "allowed_outcomes": ["approved", "conditional"],
            "min_confidence": 0.70,
        },
        category="lending",
        version="1.0",
        created_at=datetime.now(),
        updated_at=datetime.now(),
        metadata={},
    )
    engine.add_policy(policy)
    policy_id = policy.policy_id

    records = []

    # 80 compliant decisions
    for i in range(80):
        d = Decision(
            decision_id=f"compliant_{i:03d}",
            category="lending",
            scenario=f"Compliant loan application {i}",
            reasoning="Good credit profile",
            outcome="approved" if i % 2 == 0 else "conditional",
            confidence=round(0.70 + (i % 30) / 100, 2),
            timestamp=datetime.now(),
            decision_maker="officer",
        )
        records.append({"decision": d, "is_compliant": True})

    # 10 outcome violations (outcome not in allowed set)
    for i in range(10):
        d = Decision(
            decision_id=f"outcome_violation_{i:03d}",
            category="lending",
            scenario=f"Denied application {i}",
            reasoning="Poor credit history",
            outcome="denied",
            confidence=0.80,
            timestamp=datetime.now(),
            decision_maker="officer",
        )
        records.append({"decision": d, "is_compliant": False})

    # 10 confidence violations
    for i in range(10):
        d = Decision(
            decision_id=f"confidence_violation_{i:03d}",
            category="lending",
            scenario=f"Low-confidence decision {i}",
            reasoning="Insufficient data",
            outcome="approved",
            confidence=0.50,
            timestamp=datetime.now(),
            decision_maker="officer",
        )
        records.append({"decision": d, "is_compliant": False})

    return engine, policy_id, records


@pytest.fixture(scope="session")
def synthetic_compliance_engine():
    """PolicyEngine + synthetic compliant/non-compliant decisions for FNR hard gate."""
    return _make_compliance_engine()


# ---------------------------------------------------------------------------
# Scale graph fixtures for latency tests (Tracks 1.1 + 1.2)
# ---------------------------------------------------------------------------


def _load_scale_fixture(label: str) -> Optional[Dict[str, Any]]:
    fp = _fixture_path(f"decision_scale/{label}.json")
    if not fp.exists():
        return None
    return json.loads(fp.read_text(encoding="utf-8"))


def _build_scale_graph(fixture_data: Dict[str, Any]) -> Any:
    """
    Build a ContextGraph from a scale fixture using direct internal insertion
    (avoids O(n^2) sort on repeated record_decision calls).
    """
    from semantica.context.context_graph import ContextGraph

    graph = ContextGraph()

    # Initialise internal decision-tracking structures
    if not hasattr(graph, "_decisions"):
        graph._decisions = {}
        graph._decision_index = defaultdict(set)
        graph._entity_index = defaultdict(set)
        graph._temporal_index = []

    ts_base = time.time()
    for idx, d in enumerate(fixture_data["decisions"]):
        lid = d["logical_id"]
        ts = ts_base + idx * 0.0001
        record = {
            "id": lid,
            "category": d["category"],
            "scenario": d["scenario"],
            "reasoning": d["reasoning"],
            "outcome": d["outcome"],
            "confidence": d["confidence"],
            "entities": d.get("entities", []),
            "decision_maker": d.get("decision_maker", "system"),
            "timestamp": ts,
            "recorded_at": "",
            "valid_from": None,
            "valid_until": None,
            "metadata": {},
        }
        graph._decisions[lid] = record
        graph._decision_index[d["category"]].add(lid)
        for e in d.get("entities", []):
            graph._entity_index[e].add(lid)
        graph._temporal_index.append((lid, ts))

    graph._temporal_index.sort(key=lambda x: x[1])
    return graph


@pytest.fixture(scope="session")
def scale_graph_1k():
    data = _load_scale_fixture("1k")
    if data is None:
        pytest.skip("1k scale fixture missing. Run: python benchmarks/scripts/generate_precedent_scale.py")
    return _build_scale_graph(data)


@pytest.fixture(scope="session")
def scale_graph_10k():
    data = _load_scale_fixture("10k")
    if data is None:
        pytest.skip("10k scale fixture missing. Run: python benchmarks/scripts/generate_precedent_scale.py")
    return _build_scale_graph(data)


@pytest.fixture(scope="session")
def scale_graph_100k():
    data = _load_scale_fixture("100k")
    if data is None:
        pytest.skip(
            "100k scale fixture missing. "
            "Run: python benchmarks/scripts/generate_precedent_scale.py  "
            "(file > 5 MB — track via git-lfs before committing)"
        )
    return _build_scale_graph(data)


# ---------------------------------------------------------------------------
# Causal depth-latency graph fixture (Track 1.2)
# ---------------------------------------------------------------------------


def _load_causal_fixture(depth: int, size: int) -> Optional[Dict[str, Any]]:
    label = f"depth{depth}_size{size}"
    fp = _fixture_path(f"causal_depth_latency/{label}.json")
    if not fp.exists():
        return None
    return json.loads(fp.read_text(encoding="utf-8"))


def _build_causal_graph(fixture_data: Dict[str, Any]) -> Tuple[Any, str]:
    """
    Build a ContextGraph from a causal depth-latency fixture.
    Adds decisions and CAUSED edges.  Returns (graph, query_logical_id).
    """
    from semantica.context.context_graph import ContextGraph

    graph = ContextGraph()

    if not hasattr(graph, "_decisions"):
        graph._decisions = {}
        graph._decision_index = defaultdict(set)
        graph._entity_index = defaultdict(set)
        graph._temporal_index = []

    ts_base = time.time()
    for idx, d in enumerate(fixture_data["decisions"]):
        lid = d["logical_id"]
        ts = ts_base + idx * 0.0001
        record = {
            "id": lid,
            "category": d["category"],
            "scenario": d["scenario"],
            "reasoning": d["reasoning"],
            "outcome": d["outcome"],
            "confidence": d["confidence"],
            "entities": d.get("entities", []),
            "decision_maker": d.get("decision_maker", "system"),
            "timestamp": ts,
            "recorded_at": "",
            "valid_from": None,
            "valid_until": None,
            "metadata": {},
        }
        graph._decisions[lid] = record
        graph._decision_index[d["category"]].add(lid)
        for e in d.get("entities", []):
            graph._entity_index[e].add(lid)
        graph._temporal_index.append((lid, ts))
        # Also add as a proper graph node so edge traversal works
        graph.add_node(lid, node_type="Decision", content=d["scenario"])

    graph._temporal_index.sort(key=lambda x: x[1])

    # Add causal edges for the chain
    for edge in fixture_data.get("causal_edges", []):
        src = edge["source_logical_id"]
        tgt = edge["target_logical_id"]
        graph.add_edge(src, tgt, edge_type="CAUSED", weight=1.0)

    query_lid = fixture_data.get("query_logical_id", "")
    return graph, query_lid


@pytest.fixture(scope="session")
def causal_graph_depth10_10k():
    data = _load_causal_fixture(depth=10, size=10_000)
    if data is None:
        pytest.skip(
            "Causal depth-latency fixture (depth=10, size=10k) missing. "
            "Run: python benchmarks/scripts/generate_precedent_scale.py"
        )
    return _build_causal_graph(data)


# ---------------------------------------------------------------------------
# Metric utilities (shared across test modules)
# ---------------------------------------------------------------------------


def compute_mrr(ranked_lists: List[List[str]], gold_sets: List[set]) -> float:
    """Mean Reciprocal Rank."""
    rr_sum = 0.0
    for ranked, gold in zip(ranked_lists, gold_sets):
        for rank, item in enumerate(ranked, start=1):
            if item in gold:
                rr_sum += 1.0 / rank
                break
    return rr_sum / len(ranked_lists) if ranked_lists else 0.0


def compute_ndcg(ranked_list: List[str], gold_set: set, k: int = 10) -> float:
    """nDCG@k (binary relevance)."""
    import math

    dcg = 0.0
    for rank, item in enumerate(ranked_list[:k], start=1):
        if item in gold_set:
            dcg += 1.0 / math.log2(rank + 1)
    ideal = sum(1.0 / math.log2(r + 1) for r in range(1, min(len(gold_set), k) + 1))
    return dcg / ideal if ideal > 0 else 0.0


def measure_p95_ms(fn, n_trials: int = 100) -> float:
    """Run fn() n_trials times and return the P95 wall-clock time in milliseconds."""
    import statistics

    times_ms: List[float] = []
    for _ in range(n_trials):
        t0 = time.perf_counter()
        fn()
        times_ms.append((time.perf_counter() - t0) * 1_000)
    times_ms.sort()
    idx = int(len(times_ms) * 0.95)
    return times_ms[min(idx, len(times_ms) - 1)]
