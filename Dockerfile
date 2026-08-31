# syntax=docker/dockerfile:1
FROM node:26-alpine@sha256:2d984a15c9b54fd0aeb608b8e0d0d83529eb34d2966db27a1fb4f1edc3d298a3 AS frontend-builder

WORKDIR /app
COPY explorer/package*.json ./explorer/
WORKDIR /app/explorer
RUN npm ci

COPY explorer/ ./
RUN mkdir -p /app/semantica && npm run build

# CVE-2026-14456 (OpenSSL QUIC-server DoS, flagged against this base image's
# openssl/libssl3t64/openssl-provider-legacy): the Debian fix
# (3.5.7-1~deb13u2) is only in trixie-proposed-updates as of this writing,
# not yet promoted to trixie-security, so there's no package to pin here
# today. Deliberately NOT running `apt-get upgrade` to chase it - that
# breaks build reproducibility (terrascan AC_DOCKER_0052) and still
# wouldn't reach a proposed-updates-only package. Once Debian ships the fix
# and rebuilds this tag, the docker Dependabot ecosystem in
# .github/dependabot.yml opens a PR bumping the digest pin above. Also: this
# image only serves plain HTTP via uvicorn and never opens a QUIC listener,
# so the bug isn't reachable here regardless.
FROM python:3.13-slim@sha256:7ce4b6dfe35e55397b7cda544f8a13f191b7ae28dc5aad71fe664dbc9bc2623f AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FALKORDB_HOST=falkordb \
    FALKORDB_PORT=6379 \
    ALLOWED_ORIGINS=http://localhost:8000,http://127.0.0.1:8000

WORKDIR /app

RUN groupadd --system semantica \
    && useradd --system --gid semantica --home-dir /app --shell /usr/sbin/nologin semantica

COPY pyproject.toml README.md LICENSE MANIFEST.in requirements-ci.txt ./
COPY semantica/ ./semantica/
COPY integrations/ ./integrations/
COPY --from=frontend-builder /app/semantica/static ./semantica/static

# The base image ships an outdated setuptools (CVE-2025-47273); upgrade it
# explicitly since nothing in our own dependency tree otherwise pulls a
# newer copy. Pinned to the exact version requirements-ci.txt/pyproject.toml
# already build against, rather than a floor, per terrascan AC_DOCKER_0010.
# requirements-ci.txt itself carries the audited, CVE-checked pins for every
# transitive dependency (see security-scan.yml / security.yml) - feed them
# in as an unhashed constraints file (pip's hash-checking mode rejects the
# unhashable local source directory this installs) so the image lands on
# the same patched versions CI verified, e.g. msgpack>=1.2.1, rather than
# letting pip freely re-resolve and pick up an unpatched transitive version.
# (Extracted with Python's re module rather than sed/grep so there's no
# line-continuation-backslash stripping to get subtly wrong.)
RUN pip install --no-cache-dir "setuptools==84.0.0" \
    && python -c "import re, pathlib; pins = re.findall(r'^([A-Za-z0-9._-]+==\S+)', pathlib.Path('requirements-ci.txt').read_text(), re.M); pathlib.Path('/tmp/constraints.txt').write_text('\n'.join(pins))" \
    && pip install --no-cache-dir -c /tmp/constraints.txt ".[explorer]" \
    && rm -f /tmp/constraints.txt requirements-ci.txt \
    && chown -R semantica:semantica /app

USER semantica

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import json, urllib.request; data=json.load(urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3)); raise SystemExit(0 if data.get('status') == 'ok' else 1)"

CMD ["python", "-m", "uvicorn", "semantica.explorer.app:app", "--host", "0.0.0.0", "--port", "8000"]
