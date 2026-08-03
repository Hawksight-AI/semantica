#!/usr/bin/env bash
# Verifies that every third-party GitHub Action referenced in
# .github/workflows/*.yml and .github/workflows/*.yaml is pinned to a full
# commit SHA (not a mutable tag
# or branch), and that any pin's trailing "# vX" comment still matches what
# that tag resolves to today.
#
# Fails closed on purpose:
#   - a `uses:` line pinned to anything other than a 40-hex-char SHA is a
#     hard failure, not a skip - this is what stops a newly-added mutable
#     tag (e.g. `uses: some/action@v1`) from slipping past unnoticed.
#   - a tag that can't be resolved via the GitHub API (rate limit, deleted
#     tag, typo) is also a hard failure rather than a warning - an
#     unverifiable pin is exactly the failure mode this check exists to
#     catch, so it must not pass silently.
set -uo pipefail

fail=0
checked=0

# Pattern for a third-party uses: line — stored in a variable so bash's
# [[ =~ ]] parser never sees literal \" or \' escapes, which cause a
# "syntax error in conditional expression: unexpected token )" at runtime.
# Semantics: optional leading quote, owner/repo, optional subpath, @ref,
# optional trailing quote; quote chars excluded from the ref capture group.
USES_PATTERN='uses:[[:space:]]+["'"'"']?([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)(/[^[:space:]@"'"'"']+)?@([^[:space:]"'"'"']+)["'"'"']?'

while IFS=: read -r file lineno content; do
  # Local composite actions (./x) and Docker image refs (docker://...) use a
  # different pinning mechanism and aren't in scope here.
  [[ "$content" =~ uses:\ +\./ ]] && continue
  [[ "$content" =~ uses:\ +docker:// ]] && continue

  if [[ "$content" =~ $USES_PATTERN ]]; then
    repo="${BASH_REMATCH[1]}"
    ref="${BASH_REMATCH[3]}"
    checked=$((checked + 1))

    if [[ ! "$ref" =~ ^[0-9a-fA-F]{40}$ ]]; then
      echo "::error file=$file,line=$lineno::$repo is pinned to '$ref', not a full commit SHA. Mutable tags/branches can be silently re-pointed (see the LiteLLM/Trivy 2026 incident) - pin to a commit SHA instead."
      fail=1
      continue
    fi
    sha="$ref"

    if [[ "$content" =~ \#[[:space:]]*([^[:space:]]+)[[:space:]]*$ ]]; then
      tag="${BASH_REMATCH[1]}"
    else
      echo "::warning file=$file,line=$lineno::$repo@$sha has no trailing '# vX' comment recording which tag it corresponds to - add one for auditability."
      continue
    fi

    resolved=$(gh api "repos/$repo/commits/$tag" --jq '.sha' 2>/dev/null)
    if [[ -z "$resolved" ]]; then
      echo "::error file=$file,line=$lineno::Could not resolve '$repo@$tag' via the GitHub API (rate limit, deleted tag, or typo). Treating as unverifiable = failure."
      fail=1
      continue
    fi

    if [[ "$resolved" != "$sha" ]]; then
      echo "::error file=$file,line=$lineno::$repo is pinned to $sha but tag '$tag' now resolves to $resolved. Update the pin or the comment."
      fail=1
    else
      echo "OK  $repo@$tag -> $sha  ($file:$lineno)"
    fi
  fi
done < <(grep -rHn "uses:" .github/workflows/*.yml .github/workflows/*.yaml 2>/dev/null)

echo "Checked $checked action reference(s)."
exit $fail
