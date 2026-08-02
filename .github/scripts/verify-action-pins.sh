#!/usr/bin/env bash
# Verifies every SHA-pinned GitHub Action in .github/workflows/*.yml actually
# resolves to the tag named in its trailing "# vX" comment. A pin whose
# comment no longer matches the SHA it points at is exactly the kind of
# silent drift that makes SHA-pinning meaningless as an audit trail.
set -uo pipefail

fail=0

while IFS=: read -r file lineno content; do
  if [[ "$content" =~ uses:\ +([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)(/[^[:space:]@]+)?@([0-9a-fA-F]{40})[[:space:]]*#[[:space:]]*([^[:space:]]+) ]]; then
    repo="${BASH_REMATCH[1]}"
    sha="${BASH_REMATCH[3]}"
    tag="${BASH_REMATCH[4]}"

    resolved=$(gh api "repos/$repo/commits/$tag" --jq '.sha' 2>/dev/null) || {
      echo "::warning file=$file,line=$lineno::Could not resolve '$repo@$tag' via GitHub API (rate limit or tag renamed) - skipping"
      continue
    }

    if [[ "$resolved" != "$sha" ]]; then
      echo "::error file=$file,line=$lineno::$repo is pinned to $sha but tag '$tag' now resolves to $resolved. Update the pin or the comment."
      fail=1
    else
      echo "OK  $repo@$tag -> $sha  ($file:$lineno)"
    fi
  fi
done < <(grep -rn "uses:.*@[0-9a-fA-F]\{40\}" .github/workflows/*.yml)

exit $fail
