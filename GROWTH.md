# Growth & Distribution Playbook

North star: **10,000 developers who actually use Semantica in real projects**, not a raw PyPI download number. Downloads are a lagging indicator of distribution, not a target to optimize directly.

```
GitHub stars → Website visitors → PyPI installs → Weekly active users → Production deployments → Enterprise customers
```
The last two matter far more than the download count.

## Guardrails — do not do this

- No fake/looping CI jobs that repeatedly `pip install semantica` purely to inflate the graph. It's detectable, it produces zero real users, and it damages credibility with anyone doing diligence (investors, enterprise buyers, security reviewers).
- No package-splitting purely to multiply install counts — only split into `semantica-*` packages when there's a real architectural reason.
- No meaningless Docker pulls or notebook launches with no real content behind them.
- Every item below should get someone from "installed it" to "used it for something real." If a channel can't do that, it's not worth building.

## 30-day priority sprint

Ordered by leverage-to-effort ratio; do these first.

| # | Initiative | Target |
| - | ---------- | ------ |
| 1 | ✅ GitHub Actions example + reusable `setup-semantica` composite action + install-matrix badge | done |
| 2 | Google Colab notebooks | 10 |
| 3 | Docker images (RAG, Graph, Agent, API) | 4-5 |
| 4 | Hugging Face Spaces demos | 3-4 |
| 5 | LangChain integration + example | 1 |
| 6 | LlamaIndex integration + example | 1 |
| 7 | Vector/graph DB integrations (Qdrant, Weaviate, Neo4j) | 3 |
| 8 | MCP server + example | 1 (already have `mcp/` — package as a distributable example) |
| 9 | Production-quality starter repos (FastAPI, Streamlit, Gradio) | 3 |
| 10 | `awesome-rag` / `awesome-llm` / `awesome-knowledge-graph` list submissions | 3+ PRs |

Push everything through: GitHub → Discord (`sV34vps5hH`) → X (`@BuildSemantica`) → GitHub Discussions → Reddit → Hacker News → relevant newsletters.

## Full channel checklist

### CI/CD (highest-intent distribution — installs tied to real pipelines)

- [x] GitHub Actions example in `examples/ci/github-actions.yml`
- [x] Reusable composite GitHub Action — [`.github/actions/setup-semantica`](.github/actions/setup-semantica/action.yml), modeled on `actions/setup-python`; usable by any repo as `uses: semantica-agi/semantica/.github/actions/setup-semantica@main`
- [x] "pip install" status badge in the README, backed by [`.github/workflows/install-matrix.yml`](.github/workflows/install-matrix.yml) — verifies the *published* package installs cleanly on Ubuntu/macOS/Windows across Python 3.9-3.12, weekly + on every release
- [x] GitLab CI template — `examples/ci/gitlab-ci.yml`
- [x] CircleCI template — `examples/ci/circleci-config.yml`
- [ ] Jenkins, Azure DevOps, Bitbucket Pipelines, Buildkite, Travis CI equivalents

### Release pipeline hardening (already had Trusted Publishing/OIDC + SLSA attestation — this rounds it out to match top-tier OSS release practice)

- [x] `twine check` gate in `.github/workflows/release.yml` before publish — catches a broken PyPI long-description render before it goes live instead of after (a malformed README on the live PyPI page is a silent conversion killer)
- [x] `CITATION.cff` (see Academic & research below)
- [x] OpenSSF Scorecard (see Discoverability below)
- [ ] Considered and deliberately skipped: Release Drafter / auto-generated changelogs — this repo hand-curates `CHANGELOG.md` with far more detail (PR numbers, contributors, phase-1 limitations) than a bot would produce. Don't introduce this without checking with maintainers first.
- [ ] Renovate / Dependabot config templates that auto-bump the `semantica` version in downstream repos — real recurring CI runs on real adopters
- [ ] Nightly scheduled workflow template that tests a downstream project against `semantica@latest`

### Containers & dev environments

- [ ] Official Docker images: RAG, Graph, Agent, API, `+Postgres`, `+Neo4j`, `+Qdrant`
- [ ] `docker-compose` examples (repo already has `docker-compose.dev.yml` / `docker-compose.yml` as a base)
- [ ] `.devcontainer/devcontainer.json` for one-click "Reopen in Container"
- [ ] GitHub Codespaces-ready config
- [ ] Gitpod config
- [ ] "Use this template" GitHub repo button so new projects start with `semantica` in `requirements.txt`

### Notebooks & hosted demos

- [ ] 10-20 Google Colab notebooks (Graph RAG, agent memory, entity resolution, semantic search, document intelligence)
- [ ] Kaggle Notebooks/Kernels
- [ ] Binder / mybinder.org config for instant repo launch
- [ ] SageMaker Studio Lab / Databricks Community Edition / Paperspace Gradient examples
- [ ] Hugging Face Spaces (Streamlit/Gradio) demos with `semantica` in `requirements.txt`
- [ ] Public hosted playground (source on GitHub, install visible)

### Framework & data-store integrations

- [x] LangChain integration — `integrations/langchain/` (`SemanticaRetriever`, `SemanticaVectorStore`, `SemanticaKGTool`/`SemanticaDecisionTool`), `pip install semantica[langchain]`, shipped in 0.6.7
- [ ] LlamaIndex integration + example
- [ ] LangGraph example
- [ ] Neo4j integration/example (docs already list it as a supported graph store — turn into a runnable example repo)
- [ ] Vector DB examples: Qdrant, Weaviate, Milvus, Pinecone, Chroma, FAISS, pgvector, OpenSearch/Elasticsearch (FAISS/Pinecone/Weaviate/Qdrant/Milvus/PgVector already supported per `docs/community-projects.md` — package each as a standalone example)
- [ ] LLM provider quickstarts: OpenAI, Anthropic, Gemini, Groq, Ollama, HuggingFace, DeepSeek, LiteLLM (already-supported providers per docs — each gets its own copy-paste quickstart)
- [ ] CrewAI / Agno integration examples (already documented under `docs/integrations/`) — promote as standalone repos, not just docs pages

### Package managers & installers

- [ ] conda-forge feedstock
- [ ] Homebrew formula for the CLI
- [ ] Nix/nixpkgs packaging
- [ ] Chocolatey / Scoop (Windows)
- [ ] Document `uv add semantica` and `poetry add semantica` explicitly alongside `pip install`

### Downstream packages & CLI

- [ ] Genuinely useful `semantica-*` packages only where warranted (e.g. `semantica-rag`, `semantica-connectors`) — each pulls `semantica` as a real dependency
- [ ] Make sure `semantica init / ingest / index / query / serve` CLI flows are the default onboarding path in every tutorial
- [ ] VS Code extension wrapping the CLI (scaffold + run commands from the command palette)
- [ ] JetBrains plugin equivalent

### Templates & starters

- [ ] Cookiecutter templates: `cookiecutter-semantic-rag`, `cookiecutter-ai-agent`, `cookiecutter-enterprise-rag`
- [ ] Starter repos: FastAPI, Streamlit, Gradio, Next.js frontend + Semantica backend
- [ ] Cloud deploy templates: AWS, GCP, Azure, Modal, Railway, Render, Fly.io (repo already has `deploy/azure`, `deploy/gcp`, `deploy/fly`, `deploy/railway`, `deploy/render`, `deploy/kubernetes`, `deploy/helm` — link these prominently from the README/quickstart, they're already-built distribution surface)
- [ ] Terraform / Pulumi / Helm modules published to their respective registries

### Discoverability & curation

- [ ] Submit to `awesome-rag`, `awesome-llm`, `awesome-knowledge-graph`, `awesome-python`
- [ ] Pitch newsletters with engaged Python/AI audiences (Python Weekly, Import AI, TLDR AI, etc.)
- [x] PyPI trove classifiers/keywords and `project.urls` (Homepage/Docs/Repository/Changelog/Bug Tracker) — already complete in `pyproject.toml`
- [ ] Get listed on Papers With Code for any retrieval/graph-RAG benchmark work
- [x] [OpenSSF Scorecard](https://scorecard.dev/viewer/?uri=github.com/semantica-agi/semantica) badge + weekly workflow (`.github/workflows/scorecard.yml`) — a concrete trust signal security/procurement teams check before greenlighting adoption, which gates real (non-CI-bot) install growth at enterprises

### Academic & research

- [x] `CITATION.cff` at repo root — enables GitHub's native "Cite this repository" button, feeds Google Scholar/academic tooling; complements `docs/citation.md` (still needs a real Zenodo DOI to replace the `XXXXXXX` placeholder in both places once one is minted)
- [ ] arXiv paper if there's real architectural novelty to describe
- [ ] Zenodo DOI for citability (`docs/citation.md` already exists — make sure it points to a real DOI)
- [ ] Workshop/tutorial sessions at PyData/ODSC-style events with hands-on install steps
- [ ] University course material / bootcamp adoption outreach

### Content

- [ ] Reproducible benchmark repos (Graph RAG vs vector RAG, retrieval@k, enterprise-scale retrieval) with `pip install semantica && python benchmark.py`
- [ ] 20-30 real-world example applications (RAG, enterprise document intelligence, financial entity graphs, code knowledge graphs, research discovery, agent memory)
- [ ] Blog/tutorial posts on Dev.to, Medium, personal blogs — always with runnable code, not just prose
- [ ] Contribute integrations/PRs to other projects building RAG/agents/knowledge graphs — "I implemented Semantica support" beats "please use Semantica"

## Tracking

Don't just watch the raw PyPI number — use download analytics (e.g. PePy) to separate CI/bot traffic from real installs, and track the funnel above end-to-end where possible (stars → site visits → installs → weekly actives).
