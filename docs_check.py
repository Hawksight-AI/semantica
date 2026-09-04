"""Mintlify docs integrity checker — run before merging any docs PR."""
from __future__ import annotations

import glob
import json
import os
import re
import subprocess
import sys
from typing import Any, Callable, cast

try:
    from rich.console import Console as _Console
    _console = _Console()

    def _print_pass(label: str) -> None:
        _console.print(f"[bold green]pass[/bold green]  {label}")

    def _print_fail(label: str, msgs: list[str]) -> None:
        _console.print(f"[bold red]FAIL[/bold red]  {label}")
        for m in msgs:
            _console.print(f"[dim]      - {m}[/dim]")

    def _print_summary(failures: list[str]) -> None:
        _console.print()
        if failures:
            _console.print(f"[bold red]FAILED[/bold red]  {len(failures)} issue(s) found")
        else:
            _console.print("[bold green]All checks passed[/bold green]")

except ModuleNotFoundError:
    def _print_pass(label: str) -> None:  # type: ignore[misc]
        print(f"pass  {label}")

    def _print_fail(label: str, msgs: list[str]) -> None:  # type: ignore[misc]
        print(f"FAIL  {label}")
        for m in msgs:
            print(f"      - {m}")

    def _print_summary(failures: list[str]) -> None:  # type: ignore[misc]
        print()
        if failures:
            print(f"FAILED  {len(failures)} issue(s) found")
        else:
            print("All checks passed")


DOCS = "docs"
ALL_MD: list[str] = glob.glob(f"{DOCS}/**/*.md", recursive=True)

failures: list[str] = []


def check(label: str) -> Callable[[Callable[[], list[str]]], None]:
    """Decorator: run a check function, print result, collect failures."""
    def decorator(fn: Callable[[], list[str]]) -> None:
        issues = fn()
        if issues:
            _print_fail(label, issues)
            failures.extend(issues)
        else:
            _print_pass(label)
    return decorator


def read(path: str) -> str:
    return open(path, encoding="utf-8").read()


# ── 1. docs.json is valid JSON ────────────────────────────────────────────────
@check("docs.json is valid JSON")
def _() -> list[str]:
    try:
        json.loads(read(f"{DOCS}/docs.json"))
        return []
    except Exception as e:
        return [str(e)]


# ── 2. Every nav page exists on disk ─────────────────────────────────────────
@check("All nav pages exist on disk")
def _() -> list[str]:
    cfg: Any = json.loads(read(f"{DOCS}/docs.json"))

    def nav_pages(obj: Any) -> list[str]:
        """Recursively collect strings from 'pages' arrays only."""
        result: list[str] = []
        if isinstance(obj, dict):
            d = cast(dict[str, Any], obj)
            for page in cast(list[Any], d.get("pages", [])):
                if isinstance(page, str):
                    result.append(page)
                else:
                    result.extend(nav_pages(page))
            for v in d.values():
                if isinstance(v, (dict, list)):
                    result.extend(nav_pages(v))
        elif isinstance(obj, list):
            for item in cast(list[Any], obj):
                result.extend(nav_pages(item))
        return result

    return [
        f"missing: {p}"
        for p in set(nav_pages(cfg))
        if not p.startswith("http") and not os.path.exists(f"{DOCS}/{p}.md")
    ]


# ── 3. Internal Card hrefs resolve ───────────────────────────────────────────
@check("All internal Card hrefs resolve")
def _() -> list[str]:
    issues: list[str] = []
    for fpath in ALL_MD:
        for m in re.finditer(r'href=["\'](?!http)([^"\'#]+)["\']', read(fpath)):
            href = m.group(1).strip()
            target = os.path.normpath(os.path.join(os.path.dirname(fpath), href)) + ".md"
            if not os.path.exists(target):
                issues.append(f"{fpath}: href '{href}'")
    return issues


# ── 4. No stale repo URLs ─────────────────────────────────────────────────────
@check("No stale repo URLs")
def _() -> list[str]:
    stale = ["Hawksight-AI/semantica", "semantica-dev/semantica"]
    files = ALL_MD + [f"{DOCS}/docs.json"]
    return [
        f"{f}: '{pat}'"
        for f in files
        for pat in stale
        if pat in read(f)
    ]


# ── 5. All reference pages have frontmatter ───────────────────────────────────
@check("All reference pages have frontmatter")
def _() -> list[str]:
    return [
        os.path.basename(f)
        for f in glob.glob(f"{DOCS}/reference/*.md")
        if not read(f).startswith("---")
    ]


# ── 6. No known-wrong class names ────────────────────────────────────────────
@check("No known-wrong class names in reference pages")
def _() -> list[str]:
    banned: list[tuple[str, str]] = [
        (r"\bBaseIngestor\b",    "docs/architecture.md"),
        (r"\bBaseExtractor\b",   "docs/architecture.md"),
        (r"\bBasePlugin\b",      "docs/architecture.md"),
        (r"\bDataNormalizer\b",  "docs/reference/normalize.md"),
        (r"\bEntityResolver\b",  "docs/reference/deduplication.md"),
        (r"\bDeductiveEngine\b", "docs/reference/reasoning.md"),
        (r"\bAbductiveEngine\b", "docs/reference/reasoning.md"),
        (r"\bGraphMLExporter\b", "docs/reference/export.md"),
        (r"\bArangoExporter\b(?!.*AQL)",                        "docs/reference/export.md"),
        (r"(?<!Temporal)(?<!Graph)\bReasoningEngine\b",         "docs/reference/reasoning.md"),
    ]
    return [
        f"{fpath}: '{pat}'"
        for pat, fpath in banned
        if os.path.exists(fpath) and re.search(pat, read(fpath))
    ]


# ── 7. No Python 3.9+ type syntax in code blocks ─────────────────────────────
@check("No Python 3.9+ type syntax in code blocks (3.8 compat)")
def _() -> list[str]:
    issues: list[str] = []
    for fpath in ALL_MD:
        in_block = False
        for i, line in enumerate(open(fpath, encoding="utf-8"), 1):
            if line.strip().startswith("```"):
                in_block = not in_block
            if in_block and re.search(r":\s*(list|dict|tuple|set)\[", line):
                issues.append(f"{fpath}:{i}: {line.rstrip()}")
    return issues


# ── 8. index.md covers all 27 modules ────────────────────────────────────────
@check("All 27 modules present in index.md")
def _() -> list[str]:
    modules = [
        "semantica.ingest", "semantica.parse", "semantica.split", "semantica.normalize",
        "semantica.semantic_extract", "semantica.kg", "semantica.ontology", "semantica.reasoning",
        "semantica.embeddings", "semantica.vector_store", "semantica.graph_store",
        "semantica.triplet_store", "semantica.context", "semantica.provenance",
        "semantica.change_management", "semantica.deduplication", "semantica.conflicts",
        "semantica.export", "semantica.visualization", "semantica.pipeline", "semantica.seed",
        "semantica.llms", "semantica.mcp_server", "semantica.explorer", "semantica.evals",
        "semantica.utils", "semantica.core",
    ]
    index = read(f"{DOCS}/index.md")
    return [m for m in modules if m not in index]


# ── 9. JSX component tags are balanced in every page ─────────────────────────
@check("All Mintlify JSX component tags are balanced")
def _() -> list[str]:
    # Paired block-level components that must open and close.
    COMPONENTS = [
        "AccordionGroup", "Accordion", "Steps", "Step",
        "CodeGroup", "Tabs", "Tab", "CardGroup", "Card",
        "Expandable",
    ]
    issues: list[str] = []
    for fpath in ALL_MD:
        content = read(fpath)
        lines = content.splitlines()
        for comp in COMPONENTS:
            # Count opening and closing tags (ignore self-closing <Comp />)
            opens = len(re.findall(rf"<{comp}[\s>]", content))
            closes = len(re.findall(rf"</{comp}>", content))
            if opens != closes:
                issues.append(
                    f"{fpath}: <{comp}> opened {opens}x but closed {closes}x"
                )
        # Check code fences are balanced (odd fence count = unclosed block)
        fence_count = sum(
            1 for ln in lines if ln.strip().startswith("```")
        )
        if fence_count % 2 != 0:
            issues.append(f"{fpath}: odd number of ``` fences — unclosed code block")
    return issues


# ── 10. Mintlify export succeeds (requires Node.js / npx) ────────────────────
@check("Mintlify export builds without errors")
def _() -> list[str]:
    npx = "npx.cmd" if sys.platform == "win32" else "npx"
    try:
        result = subprocess.run(
            [npx, "--yes", "mintlify@4.2.632", "export", "--output", "export_ci_check.zip"],
            cwd=DOCS,
            capture_output=True,
            text=True,
            timeout=600,
        )
        # Clean up zip regardless of outcome
        zip_path = os.path.join(DOCS, "export_ci_check.zip")
        if os.path.exists(zip_path):
            os.remove(zip_path)

        combined = (result.stdout or "") + (result.stderr or "")

        if result.returncode != 0:
            # On Windows, npm cleanup raises EPERM on temp dirs — not a real
            # export failure. Treat as a skip rather than a hard failure.
            if sys.platform == "win32" and "EPERM" in combined and \
                    "could not be generated" not in combined:
                return []  # Windows temp-cleanup noise; real CI runs on Linux

            # Show first 60 lines (where per-page errors are logged) AND
            # last 20 lines (where the summary error appears).
            all_lines = combined.strip().splitlines()
            head = "\n".join(all_lines[:60])
            tail = "\n".join(all_lines[-20:]) if len(all_lines) > 60 else ""
            output = head + ("\n...\n" + tail if tail else "")
            return [f"mintlify export failed (exit {result.returncode}):\n{output}"]
        return []
    except FileNotFoundError:
        return ["npx not found — skipping Mintlify export check (Node.js required)"]
    except subprocess.TimeoutExpired:
        return ["mintlify export timed out after 600 s"]


# ── Summary ───────────────────────────────────────────────────────────────────
_print_summary(failures)
if failures:
    sys.exit(1)
