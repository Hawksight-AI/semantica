"""
Generate synthetic precedent scale fixtures and causal depth-latency fixtures.

Outputs
-------
benchmarks/fixtures/decision_scale/1k.json        (< 1 MB  — committed normally)
benchmarks/fixtures/decision_scale/10k.json       (~ 5 MB  — committed via git-lfs)
benchmarks/fixtures/decision_scale/100k.json      (~ 50 MB — committed via git-lfs)
benchmarks/fixtures/causal_depth_latency/<depth>_<size>.json

Run once and commit the outputs.  Do not re-run after committing.

Usage:
    python benchmarks/scripts/generate_precedent_scale.py [--scales 1k 10k] [--no-100k]
"""

import argparse
import json
import pathlib
import sys

BENCHMARKS_ROOT = pathlib.Path(__file__).resolve().parents[1]
SCALE_PATH = BENCHMARKS_ROOT / "fixtures" / "decision_scale"
CAUSAL_PATH = BENCHMARKS_ROOT / "fixtures" / "causal_depth_latency"

CATEGORIES = 100
ENTITIES = 50
OUTCOMES = ["approved", "denied", "conditional", "deferred"]
DECISION_MAKERS = [f"officer_{i}" for i in range(10)]


def generate_decisions(n: int, prefix: str = "s") -> list[dict]:
    decisions = []
    for i in range(n):
        decisions.append(
            {
                "logical_id": f"{prefix}_{i:08d}",
                "category": f"cat_{i % CATEGORIES:03d}",
                "scenario": f"Precedent scenario {i}: evaluate applicant profile for category {i % CATEGORIES}",
                "reasoning": f"Standard assessment for case {i} in category {i % CATEGORIES}",
                "outcome": OUTCOMES[i % len(OUTCOMES)],
                "confidence": round(0.60 + (i % 41) / 100, 2),
                "entities": [f"entity_{i % ENTITIES:03d}"],
                "decision_maker": DECISION_MAKERS[i % len(DECISION_MAKERS)],
            }
        )
    return decisions


def generate_scale_fixture(n: int, label: str) -> None:
    SCALE_PATH.mkdir(parents=True, exist_ok=True)
    path = SCALE_PATH / f"{label}.json"
    if path.exists():
        print(f"  {path} already exists — skipping (delete to regenerate)")
        return
    decisions = generate_decisions(n, prefix=label.replace("k", "k"))
    fixture = {
        "meta": {
            "scale": label,
            "total_decisions": n,
            "categories": CATEGORIES,
            "entities": ENTITIES,
            "description": f"Synthetic {label} decision fixture for P95 latency benchmarks.",
        },
        "decisions": decisions,
    }
    path.write_text(json.dumps(fixture))
    size_kb = path.stat().st_size // 1024
    print(f"  Written {n:,} decisions -> {path} ({size_kb} KB)")
    if size_kb > 5_000:
        print(f"  NOTE: {path.name} is > 5 MB — track via git-lfs before committing.")


def generate_causal_fixture(depth: int, size: int) -> None:
    """Linear causal chain of `depth` decisions inside a graph of `size` total nodes."""
    CAUSAL_PATH.mkdir(parents=True, exist_ok=True)
    label = f"depth{depth}_size{size}"
    path = CAUSAL_PATH / f"{label}.json"
    if path.exists():
        print(f"  {path} already exists — skipping")
        return

    chain_ids = [f"chain_{label}_{i:06d}" for i in range(depth)]
    background_ids = [f"bg_{label}_{i:06d}" for i in range(size - depth)]

    decisions = []
    for i, lid in enumerate(chain_ids):
        decisions.append(
            {
                "logical_id": lid,
                "category": "causal_chain",
                "scenario": f"Chain node {i} at depth {depth}",
                "reasoning": f"Causal step {i}",
                "outcome": "approved",
                "confidence": 0.9,
                "entities": [f"chain_entity_{label}"],
                "decision_maker": "system",
                "role": "chain",
            }
        )
    for i, lid in enumerate(background_ids):
        decisions.append(
            {
                "logical_id": lid,
                "category": f"bg_cat_{i % 20}",
                "scenario": f"Background decision {i}",
                "reasoning": "Background reasoning",
                "outcome": "denied",
                "confidence": 0.5,
                "entities": [f"bg_entity_{i % 10}"],
                "decision_maker": "system",
                "role": "background",
            }
        )

    # Causal edges: chain[0] → chain[1] → ... → chain[depth-1]
    causal_edges = [
        {"source_logical_id": chain_ids[i], "target_logical_id": chain_ids[i + 1]}
        for i in range(depth - 1)
    ]

    fixture = {
        "meta": {
            "depth": depth,
            "graph_size": size,
            "chain_length": depth,
            "background_nodes": size - depth,
            "description": f"Causal depth-latency fixture: depth={depth}, graph_size={size}.",
        },
        "decisions": decisions,
        "causal_edges": causal_edges,
        "query_logical_id": chain_ids[-1],
    }
    path.write_text(json.dumps(fixture))
    size_kb = path.stat().st_size // 1024
    print(f"  Written depth={depth}, size={size} -> {path} ({size_kb} KB)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-100k", action="store_true", help="Skip 100k fixture generation")
    parser.add_argument("--no-causal", action="store_true", help="Skip causal depth fixtures")
    args = parser.parse_args()

    print("Generating precedent scale fixtures...")
    generate_scale_fixture(1_000, "1k")
    generate_scale_fixture(10_000, "10k")
    if not args.no_100k:
        generate_scale_fixture(100_000, "100k")
    else:
        print("  Skipping 100k fixture (--no-100k)")

    if not args.no_causal:
        print("\nGenerating causal depth-latency fixtures...")
        for depth in [3, 5, 8, 10]:
            for size in [500, 1_000, 5_000, 10_000]:
                generate_causal_fixture(depth, size)

    print("\nDone.")
    print("Remember: track benchmarks/fixtures/decision_scale/10k.json and 100k.json via git-lfs.")


if __name__ == "__main__":
    main()
