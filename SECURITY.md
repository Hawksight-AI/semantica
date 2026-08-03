# Security Policy

## Supported Versions

We actively support the following versions of Semantica with security updates:

| Version | Supported          |
| ------- | ------------------ |
| 0.2.3   | :white_check_mark: |
| 0.2.2   | :white_check_mark: |
| 0.2.1   | :white_check_mark: |
| 0.2.0   | :white_check_mark: |
| 0.1.1   | :white_check_mark: |
| 0.1.0   | :white_check_mark: |
| < 0.1.0 | :x:                |

## Reporting a Vulnerability

We take security vulnerabilities seriously. If you discover a security vulnerability, please follow these steps:

### 1. **Do NOT** create a public GitHub issue

Security vulnerabilities should be reported privately to prevent potential exploitation.

### 2. Report Security Issue

Create a [GitHub Security Advisory](https://github.com/semantica-agi/semantica/security/advisories/new) or contact us via the security email listed in `SUPPORT.md`.

Include the following information:

- **Type of vulnerability** (e.g., XSS, SQL injection, authentication bypass)
- **Affected component** (module, function, or file)
- **Steps to reproduce** (detailed description or proof-of-concept code)
- **Potential impact** (what could an attacker do?)
- **Suggested fix** (if you have one)
- **Your contact information** (for follow-up questions)

### 3. Response Timeline

- **Initial Response**: Within 24 hours for critical issues; within 48 hours for non-critical issues
- **Status Update**: Within 7 days
- **Resolution**: Depends on severity and complexity

### 4. Disclosure Policy

- We will acknowledge receipt of your report within 48 hours
- We will provide regular updates on the status of the vulnerability
- Once fixed, we will credit you (if desired) in the security advisory
- We will coordinate public disclosure with you

## Security Update Process

1. **Assessment**: We assess the severity using CVSS scoring
2. **Fix Development**: We develop and test a fix
3. **Release**: We release a security update
4. **Advisory**: We publish a security advisory on GitHub
5. **Communication**: We notify users through appropriate channels

## Severity Levels

### Critical
- Remote code execution
- Authentication bypass
- Data breach or exposure
- **Response Time**: Immediate (within 24 hours)

### High
- Privilege escalation
- Significant data leakage
- Denial of service
- **Response Time**: Within 7 days

### Medium
- Information disclosure
- Cross-site scripting (XSS)
- CSRF vulnerabilities
- **Response Time**: Within 30 days

### Low
- Minor information leakage
- Best practice violations
- **Response Time**: Next release cycle

## Known Security Considerations

### Dependencies

We regularly update dependencies to address security vulnerabilities. However, you should:

- Keep your dependencies up to date
- Review security advisories for our dependencies
- Use tools like `pip-audit` or `safety` to check for known vulnerabilities

### API Keys and Credentials

- **Never commit API keys or credentials** to the repository
- Use environment variables or secure configuration management
- Rotate keys regularly
- Use least-privilege access principles

### Data Handling

- Be cautious when processing untrusted data
- Validate and sanitize all inputs
- Use parameterized queries for database operations
- Implement rate limiting for public APIs

### Network Security

- Use HTTPS for all network communications
- Validate SSL/TLS certificates
- Be cautious with external API calls
- Implement proper authentication and authorization

## CI/CD Supply-Chain Security

Semantica's build and release pipeline is explicitly hardened against
CI/CD supply-chain attacks — the class of attack behind the March 2026
LiteLLM/Trivy incident, where a compromised third-party Action with a
**mutable tag** was used to steal a long-lived publishing token, after which
malicious packages were pushed straight to PyPI without ever touching the
source repository. Every control below maps directly to closing one step of
that attack chain.

### Immutable build inputs

- **Risk**: a tag (`@v4`, `@release/v1`) is re-pointed by a compromised upstream maintainer or account, silently changing what every consumer's CI runs.
  **Control**: every third-party GitHub Action in every workflow is pinned to a full 40-character commit SHA, with the human-readable tag kept only as a trailing comment (e.g. `actions/checkout@3d3c42e... # v7`).
- **Risk**: a SHA pin drifts out of sync with its own comment over time, or is mistyped.
  **Control**: `verify-action-pins.yml` fails closed on any `uses:` reference that isn't a full commit SHA (catching a newly added mutable tag, not just auditing existing pins), resolves every pinned tag via the GitHub API on each workflow change, on every push to `main`, and weekly, and fails if the SHA no longer matches the tag it claims to be — an API lookup that can't be resolved is treated as a failure, not a silent skip.
- **Risk**: manually re-pinning ~15 actions across 8 workflow files on every upstream release is error-prone.
  **Control**: Dependabot (`github-actions` ecosystem) opens a grouped PR that bumps the SHA *and* the tag comment together whenever an action releases — pins never require hand-editing.

### Publishing pipeline (highest-privilege path)

- **Risk**: a long-lived `PYPI_TOKEN` sitting in repo/org secrets is exfiltrated by any compromised step.
  **Control**: PyPI publishing uses Trusted Publishing (OIDC) (`id-token: write`) — there is no long-lived PyPI credential anywhere in this repository to steal.
- **Risk**: a compromised CI run publishes to PyPI with no human in the loop.
  **Control**: the publish job runs only inside a protected `pypi` GitHub Environment with a required human reviewer — every release needs manual approval in the Actions UI before it runs.
- **Risk**: the release job could be triggered from an arbitrary branch/ref.
  **Control**: the `pypi` environment's deployment-branch policy is restricted to `v*` tags only.
- **Risk**: a scanner or unrelated job inherits publish-level credentials.
  **Control**: `release.yml` sets `permissions: contents: read` at the workflow level; `contents: write` / `id-token: write` / `attestations: write` are granted only to the release job, never workflow-wide.
- **Risk**: two tag pushes race through the publish pipeline simultaneously.
  **Control**: `concurrency: group: release-${{ github.ref }}` serializes releases per tag.
- **Risk**: a consumer can't verify a wheel on PyPI actually came from this repo's CI.
  **Control**: SLSA build provenance is attested for every release via `actions/attest-build-provenance`, producing a signed, verifiable record of the exact commit and workflow run that produced the artifact (checkable with `gh attestation verify`).

### Repository controls

- **Risk**: unreviewed or force-pushed changes land on `main`.
  **Control**: `main` requires 1 approving PR review (stale approvals dismissed on new pushes), resolved conversations, and blocks force-pushes and branch deletion.
- **Risk**: a PR merges without its security/CI checks passing.
  **Control**: merges require the `build`, `Analyze Python` (CodeQL), and `security-scan` checks to pass, in strict mode (checks must be re-run against the latest `main`).
- **Risk**: a compromised scanner job reaches secrets or write access.
  **Control**: scanning jobs (`CodeQL`, `security-scan.yml`, `security.yml`, `defender-for-devops.yml`) run with read-only, least-privilege permissions (typically `contents: read` + `security-events: write` only) and never share a job, environment, or secret scope with the publish job.
- **Risk**: secrets are committed accidentally.
  **Control**: GitHub secret scanning and push protection are both enabled at the repository level, rejecting pushes that contain recognizable credential patterns before they land in history.

## Automated Security Scanning

Every scan below runs continuously in CI, not just at release time:

- **CodeQL** (`security-and-quality` query pack) — Python source: injection, unsafe deserialization, and other code-level vulnerability classes. Runs in `codeql.yml` on every push/PR to `main` and weekly.
- **Bandit** — Python-specific security anti-patterns (hardcoded secrets, unsafe `eval`/`pickle`, weak crypto, etc.); CI fails on any HIGH-severity finding. Runs in `security-scan.yml` on every push/PR to `main` and twice weekly.
- **Semgrep** (`p/security` ruleset) — cross-language static-analysis security patterns. Runs in `security-scan.yml` on every push/PR to `main` and twice weekly.
- **Safety** — known CVEs in Semantica's own installed dependencies, including optional LLM-provider extras such as LiteLLM; CI fails on any match. Runs in `security-scan.yml` on every push/PR to `main` and twice weekly.
- **pip-audit** — independent, PyPA-maintained vulnerability database cross-check against installed dependencies (Safety and pip-audit use different advisory sources, so both run). Runs in `security.yml` weekly.
- **Microsoft Defender for DevOps** (`eslint`, `templateanalyzer`, `terrascan`) — JavaScript/TypeScript lint-security rules and infrastructure-as-code misconfigurations. Runs in `defender-for-devops.yml` on every push/PR to `main` and weekly.
- **Checkov** — Kubernetes, Helm, Dockerfile, GitHub Actions, and secrets-pattern IaC scanning; results upload to the same Security tab as CodeQL. Runs in `defender-for-devops.yml` on every push/PR to `main` and weekly.
- **GitGuardian** — secret-detection check on every pull request, installed as a GitHub App integration (not a repo-local workflow). Runs on every PR.
- **GitHub secret scanning + push protection** — blocks known credential patterns before they're pushed, and continuously scans existing history. Platform-level, continuous.
- **Dependabot** — version/security PRs for Python, Docker, and GitHub Actions dependencies, grouped where relevant to reduce review noise. Configured in `.github/dependabot.yml`, runs weekly for security-relevant packages and monthly for docs dependencies.
- **`verify-action-pins.yml`** — enforces that every Action reference is a full commit SHA (failing on a newly introduced mutable tag) and confirms each SHA still matches the tag it claims to be. Runs on every workflow change, every push to `main`, and weekly.

All SARIF-producing scanners (CodeQL, Checkov, Microsoft Defender) publish
findings to the repository's **Security → Code scanning alerts** tab, giving
a single audit trail across tools rather than scattered per-tool reports.

### Adopting this posture in a fork or downstream deployment

Teams standing up their own instance of Semantica, or forking it for an
internal/regulated deployment, can reuse this posture directly:

1. Keep Dependabot's `github-actions` ecosystem entry — it is what keeps
   SHA pins current without manual maintenance.
2. Re-run `verify-action-pins.yml` after re-pointing the repository's Actions
   at your own mirrors, if you do so.
3. If you publish your own PyPI package from a fork, configure your own
   Trusted Publishing trust relationship on PyPI (Trusted Publishing is
   scoped to a specific `owner/repo` + workflow filename) and your own
   protected environment with your own required reviewers — these are not
   transferable from this repository.
4. Branch protection, environment protection, and repository secret
   scanning are repository *settings*, not workflow files — cloning or
   forking the repo does **not** copy them. They must be re-applied via
   the GitHub UI or API on the new repository.
5. GitHub secret scanning and push protection are repository settings that
   don't carry over to a fork either — re-enable both under the new
   repository's Security settings, not just Dependabot.
6. GitGuardian runs as a GitHub App installation scoped to this specific
   repository, not a workflow file — a fork gets no secret-detection
   coverage from it until the app is installed separately on the new repo.
7. CodeQL's `upload-sarif` step in `codeql.yml` only runs meaningfully if
   Default Setup is *not* already enabled for the repository (it's designed
   to skip gracefully otherwise) — check whether Default Setup or Advanced
   Setup is active on the new repository and adjust expectations for where
   CodeQL findings show up accordingly.

## Dependency Security Policy

### Regular Updates

- We monitor security advisories for all dependencies
- We update dependencies regularly in our development branch
- Critical security updates are backported to supported versions

### Reporting Dependency Vulnerabilities

If you discover a vulnerability in one of our dependencies:

1. Check if it's already reported upstream
2. Report to us if it affects Semantica specifically
3. We will coordinate with upstream maintainers if needed

### Security Scanning

We use automated tools to scan for vulnerabilities:

- **Dependabot**: Automated dependency updates and security alerts
- **GitHub Security Advisories**: Vulnerability tracking
- **Manual Reviews**: Regular security audits

## Best Practices for Users

1. **Keep Semantica Updated**: Always use the latest stable version
2. **Review Dependencies**: Regularly update your project dependencies
3. **Secure Configuration**: Use secure defaults and proper configuration
4. **Monitor Logs**: Watch for suspicious activity
5. **Report Issues**: Don't hesitate to report potential security issues

## Security Acknowledgments

We appreciate responsible disclosure. Security researchers who help us improve the security of Semantica will be:

- Credited in security advisories (if desired)
- Listed in our security acknowledgments
- Recognized for their contribution

## Contact

For security-related questions or concerns:

- **Private Reporting**: Please do not report vulnerabilities in public issues.
- **GitHub Security Advisories**: [Report vulnerability](https://github.com/semantica-agi/semantica/security/advisories/new)

## Additional Resources

- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [Python Security Best Practices](https://python.readthedocs.io/en/latest/library/security.html)
- [GitHub Security Best Practices](https://docs.github.com/en/code-security)

---

**Thank you for helping keep Semantica and its users safe!**

