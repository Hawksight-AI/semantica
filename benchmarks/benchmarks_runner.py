import argparse
import os
import subprocess
import sys
from datetime import datetime

from rich.console import Console
from rich.rule import Rule

console = Console()

from typing import List
def _discover_modules() -> List[str]:
    benchmarks_dir = "benchmarks"
    _excluded = {"results", "__pycache__"}
    return sorted(
        d for d in os.listdir(benchmarks_dir)
        if os.path.isdir(os.path.join(benchmarks_dir, d))
        and not d.startswith(("_", "."))
        and d not in _excluded
    )


def run_benchmarks():
    """
    Master Runner for Semantica Benchmarks.
    """
    available_modules = _discover_modules()

    parser = argparse.ArgumentParser(description="Run Semantica Benchmarks")
    parser.add_argument(
        "--strict", action="store_true", help="Fail script if performance regresses"
    )
    parser.add_argument(
        "--module",
        type=str,
        choices=available_modules,
        help=(
            "Run benchmarks for a specific module only "
            "(default: all modules). "
            f"Available: {', '.join(available_modules)}"
        ),
    )
    args = parser.parse_args()

    console.print(Rule("[bold cyan]Semantica Benchmark Suite[/bold cyan]", style="cyan"))

    timestamp = datetime.now().strftime("%Y%m%d_%H_%M_%S")
    os.makedirs("benchmarks/results", exist_ok=True)

    current_json = f"benchmarks/results/run_{timestamp}.json"
    baseline_json = "benchmarks/results/baseline.json"

    if args.module:
        test_path = os.path.join("benchmarks", args.module)
        if not os.path.isdir(test_path):
            console.print(
                f"[bold red] ✗[/bold red] Module directory not found: {test_path}"
            )
            sys.exit(1)
        console.print(f"[dim]Module filter:[/dim] {args.module}")
    else:
        test_path = "benchmarks/"

    cmd = [
        sys.executable,
        "-m",
        "pytest",
        test_path,
        "-p", "no:typeguard",
        "-p", "no:langsmith",
        "--benchmark-only",
        f"--benchmark-json={current_json}",
        "--benchmark-columns=min,mean,stddev,ops",
        "--benchmark-sort=mean",
    ]

    console.print(f"[dim]Saving results to[/dim] {current_json}")
    result = subprocess.run(cmd)

    if result.returncode != 0:
        console.print("[bold red] ✗[/bold red] Benchmarks failed to execute (runtime errors).")
        sys.exit(result.returncode)

    console.print("[bold green] ✓[/bold green] Benchmarks completed execution.")

    if os.path.exists(baseline_json):
        console.print(f"[dim]Comparing against baseline:[/dim] {baseline_json}")

        if os.path.exists("benchmarks/infrastructure/compare.py"):
            compare_cmd = [
                sys.executable,
                "benchmarks/infrastructure/compare.py",
                baseline_json,
                current_json,
            ]

            compare_result = subprocess.run(compare_cmd)

            if compare_result.returncode != 0:
                console.print(Rule(style="red"))
                console.print("[bold red]  PERFORMANCE REGRESSION DETECTED[/bold red]")
                console.print(Rule(style="red"))
                if args.strict:
                    sys.exit(1)
            else:
                console.print(
                    "[bold green] ✓[/bold green] Performance is within acceptable limits."
                )
        else:
            console.print(
                "[bold yellow] ⚠[/bold yellow] Comparison script not found "
                "(benchmarks/infrastructure/compare.py). Skipping comparison."
            )
    else:
        console.print(
            "[bold yellow] ⚠[/bold yellow] No baseline found. "
            "This run effectively sets the new baseline."
        )

    console.print(
        f"\n[dim]To update baseline:[/dim]  cp {current_json} {baseline_json}"
    )


if __name__ == "__main__":
    run_benchmarks()
