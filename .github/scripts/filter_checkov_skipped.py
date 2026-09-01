"""Drop checkov-suppressed results from its SARIF output before upload.

checkov's SARIF exporter includes every evaluated check as an ordinary
result, including ones it internally marked SKIPPED via an inline
`# checkov:skip=` comment or a `checkov.io/skipN` resource annotation - it
never uses SARIF's `suppressions` field, and never drops them. checkov's
JSON output *does* correctly record which checks were skipped, so this
cross-references the two: any SARIF result whose (check_id, file) pair
appears in the JSON's skipped_checks is removed before GitHub ever sees it.

Without this, every already-suppressed finding reopens as a brand new code
scanning alert on every run, forever (see #6035/#6036, #6112-6115,
#6128-6131 for the pattern this was chasing before this script existed).

Usage: filter_checkov_skipped.py <json_path> <sarif_in_path> <sarif_out_path>
"""

import json
import sys


def path_suffix(path: str, segments: int = 2) -> str:
    """Last N path segments, normalized to forward slashes, lowercased.

    checkov's JSON file_path and SARIF artifactLocation.uri are relative to
    different roots (the scanned directory vs. a temp helm-render dir), so
    they can't be compared directly - but the last couple of segments
    (e.g. "templates/service.yaml") are stable across both and specific
    enough in practice to avoid cross-file collisions.
    """
    normalized = path.replace("\\", "/").strip("/")
    return "/".join(normalized.split("/")[-segments:]).lower()


def main() -> None:
    json_path, sarif_in_path, sarif_out_path = sys.argv[1:4]

    with open(json_path, encoding="utf-8") as f:
        checkov_json = json.load(f)
    if isinstance(checkov_json, dict):
        checkov_json = [checkov_json]

    skipped = set()
    for block in checkov_json:
        for check in block.get("results", {}).get("skipped_checks", []):
            skipped.add((check["check_id"], path_suffix(check["file_path"])))

    with open(sarif_in_path, encoding="utf-8") as f:
        sarif = json.load(f)

    removed = 0
    for run in sarif.get("runs", []):
        kept = []
        for result in run.get("results", []):
            rule_id = result.get("ruleId")
            locations = result.get("locations") or [{}]
            uri = (
                locations[0]
                .get("physicalLocation", {})
                .get("artifactLocation", {})
                .get("uri", "")
            )
            if (rule_id, path_suffix(uri)) in skipped:
                removed += 1
                continue
            kept.append(result)
        run["results"] = kept

    with open(sarif_out_path, "w", encoding="utf-8") as f:
        json.dump(sarif, f)

    print(f"Removed {removed} checkov-suppressed result(s) from the SARIF before upload.")


if __name__ == "__main__":
    main()
