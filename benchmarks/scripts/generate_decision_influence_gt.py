"""
Generate benchmarks/fixtures/decision_influence_ground_truth.json

500 synthetic decisions organised in 50 clusters of 10.
Each cluster has a unique category and a unique shared entity so that
ContextGraph.analyze_decision_influence() (which uses the entity index) can
find exactly the 9 non-query members of the cluster with zero false positives.

Run once and commit the output.  Do not re-run after committing.

Usage:
    python benchmarks/scripts/generate_decision_influence_gt.py
"""

import json
import pathlib

CLUSTERS = 50
MEMBERS_PER_CLUSTER = 10
FIXTURE_PATH = pathlib.Path(__file__).resolve().parents[1] / "fixtures" / "decision_influence_ground_truth.json"


def main() -> None:
    FIXTURE_PATH.parent.mkdir(parents=True, exist_ok=True)

    decisions: list[dict] = []
    queries: list[dict] = []

    for c in range(CLUSTERS):
        category = f"cluster_{c:02d}"
        shared_entity = f"cluster_entity_{c:02d}"
        logical_ids: list[str] = []

        for m in range(MEMBERS_PER_CLUSTER):
            logical_id = f"dec_{c:02d}_{m:02d}"
            decisions.append(
                {
                    "logical_id": logical_id,
                    "category": category,
                    "scenario": f"Cluster {c} decision {m}: evaluate case under category {category}",
                    "reasoning": f"Standard reasoning for cluster {c}, member {m}",
                    "outcome": "approved" if m % 3 != 2 else "denied",
                    "confidence": round(0.75 + (m % 5) * 0.05, 2),
                    "entities": [shared_entity],
                    "decision_maker": f"officer_{c % 10}",
                }
            )
            logical_ids.append(logical_id)

        query_logical_id = logical_ids[0]
        influenced = logical_ids[1:]

        queries.append(
            {
                "query_logical_id": query_logical_id,
                # depth_3 and depth_5 are identical because analyze_decision_influence
                # uses the entity index (depth-agnostic direct matching).
                "depth_3_influenced_logical_ids": influenced,
                "depth_5_influenced_logical_ids": influenced,
            }
        )

    fixture = {
        "meta": {
            "total_decisions": len(decisions),
            "total_queries": len(queries),
            "clusters": CLUSTERS,
            "members_per_cluster": MEMBERS_PER_CLUSTER,
            "description": (
                "Synthetic ground-truth fixture for decision influence benchmarks. "
                "Each cluster shares a unique entity so the API finds exactly the "
                "intended downstream decisions with zero spurious results."
            ),
        },
        "decisions": decisions,
        "queries": queries,
    }

    FIXTURE_PATH.write_text(json.dumps(fixture, indent=2))
    print(f"Written {len(decisions)} decisions and {len(queries)} queries -> {FIXTURE_PATH}")


if __name__ == "__main__":
    main()
