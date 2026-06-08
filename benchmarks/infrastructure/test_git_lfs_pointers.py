"""
Git LFS pointer validation for benchmark infrastructure (Issue #575).

Validates that large files are properly tracked by git LFS to ensure
benchmark dataset registry remains manageable as module tracks expand.
"""

import pytest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCHMARK_ROOT = REPO_ROOT / "benchmarks"


@pytest.mark.skip(reason="LFS dataset registry not yet implemented (#575)")
def test_lfs_configured_for_benchmark_datasets():
    """Check .gitattributes contains LFS patterns scoped to benchmark dataset files."""
    gitattributes = REPO_ROOT / ".gitattributes"
    assert gitattributes.exists(), ".gitattributes not found at repo root"

    content = gitattributes.read_text()
    has_lfs_config = any(
        "filter=lfs" in line
        for line in content.splitlines()
        if line.startswith("benchmarks/")
    )
    assert has_lfs_config, (
        "No LFS patterns found for benchmarks/ in .gitattributes; "
        "add scoped tracking e.g. 'benchmarks/datasets/**/*.parquet filter=lfs diff=lfs merge=lfs -text'"
    )


@pytest.mark.skip(reason="Module track directories not yet created (#575)")
def test_benchmark_directories_structure():
    """Validate benchmark directory structure aligns with issue #575 module tracks."""
    expected_dirs = [
        "context_graph_effectiveness",
        "decision_intelligence",
        "temporal_provenance",
        "memory_context",
        "structural_intelligence",
        "module_tracks",
    ]

    missing_dirs = [d for d in expected_dirs if not (BENCHMARK_ROOT / d).exists()]
    assert not missing_dirs, f"Expected benchmark directories missing: {missing_dirs}"


def test_no_large_files_in_benchmarks_without_lfs():
    """Ensure no large files (>1 MB) are committed without LFS tracking."""
    skip_suffixes = {".py", ".md", ".txt", ".rst"}
    large_files = []

    for p in BENCHMARK_ROOT.rglob("*"):
        if not p.is_file() or "results" in p.parts or p.suffix in skip_suffixes:
            continue
        try:
            if p.stat().st_size > 1_000_000:
                large_files.append(str(p.relative_to(BENCHMARK_ROOT)))
        except OSError:
            continue

    assert not large_files, (
        f"Large files found without LFS tracking: {large_files}. "
        "Track them with: git lfs track <pattern>"
    )


def test_infrastructure_directory_exists():
    """Basic validation that benchmarks/infrastructure directory exists."""
    infra_dir = BENCHMARK_ROOT / "infrastructure"
    assert infra_dir.is_dir(), "benchmarks/infrastructure directory should exist"
