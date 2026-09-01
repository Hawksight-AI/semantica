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

COPY pyproject.toml README.md LICENSE MANIFEST.in \
     .github/requirements/explorer-extra-py313.txt .github/requirements/pep517-build.txt ./
COPY semantica/ ./semantica/
COPY integrations/ ./integrations/
COPY --from=frontend-builder /app/semantica/static ./semantica/static

# explorer-extra-py313.txt is `uv pip compile pyproject.toml --extra explorer
# --python-version 3.13 --constraint requirements-ci.txt --generate-hashes`
# (see ci.yml's explorer-extra-py311.txt for the CI counterpart, resolved
# for CI's python 3.11 instead - the two aren't interchangeable: audioread
# (via librosa) needs standard-aifc/standard-sunau only on python>=3.13,
# since aifc/sunau left stdlib there, so a 3.11-resolved lockfile is
# missing hashes pip needs on this image's actual 3.13 interpreter and
# --require-hashes fails outright rather than silently under-pinning).
# Every fetched package is hash-verified (Scorecard Pinned-Dependencies)
# and pinned to the same versions CI audited, e.g. msgpack==1.2.1 and
# setuptools==84.0.0 (which also replaces the base image's vulnerable
# 70.3.0, CVE-2025-47273 - nothing else in the tree pulls a newer copy).
# --no-deps on the local package itself: it's our own source tree, not a
# fetch, so there's nothing to hash-pin there - but `pip install .` still
# does a PEP 517 build, which by default creates an *isolated* build env
# and fetches [build-system] requires (setuptools, wheel) completely
# outside any hash checking. pep517-build.txt pins that exact
# build-system.requires; installing it first and passing
# --no-build-isolation makes pip reuse those hash-verified copies instead
# of fetching its own.
RUN pip install --no-cache-dir -r explorer-extra-py313.txt -r pep517-build.txt --require-hashes \
    && pip install --no-cache-dir --no-deps --no-build-isolation . \
    && rm -f explorer-extra-py313.txt pep517-build.txt \
    && chown -R semantica:semantica /app

USER semantica

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import json, urllib.request; data=json.load(urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3)); raise SystemExit(0 if data.get('status') == 'ok' else 1)"

CMD ["python", "-m", "uvicorn", "semantica.explorer.app:app", "--host", "0.0.0.0", "--port", "8000"]
