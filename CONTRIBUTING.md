# Contributing to Semantica

Thank you for your interest in contributing! Every contribution, no matter how small, is valuable. 🎉

⭐ **Give us a Star** • 🍴 **[Fork Semantica](https://github.com/semantica-agi/semantica/fork)** • 💬 **Join our [Discord](https://discord.gg/sV34vps5hH)**

> **New to contributing?** Start with a [`good first issue`](https://github.com/semantica-agi/semantica/labels/good%20first%20issue) or join our [Discord](https://discord.gg/sV34vps5hH) community.

---

## 🚀 Quick Start

1. Find a [`good first issue`](https://github.com/semantica-agi/semantica/labels/good%20first%20issue)
2. [Fork Semantica](https://github.com/semantica-agi/semantica/fork) & clone the repository
3. Make your changes
4. Submit a pull request!

**Need help?** Join [Discord](https://discord.gg/sV34vps5hH) or [GitHub Discussions](https://github.com/semantica-agi/semantica/discussions)

---

## 🗂️ Working on an Existing Issue

If you want to work on an open GitHub issue, please follow these steps to keep things coordinated and avoid duplicate effort:

1. **Check the issue.** Look at the issue's assignees and recent comments. If someone is already actively working on it, consider a different issue or ask in the comments whether help is welcome.

2. **Comment if you'd like the issue reserved.** Leaving a comment like *"I'd like to take this on"* is the fastest way to get assigned, but it isn't required — maintainers can also assign an issue directly to a contributor (e.g., based on recent activity in the repo) without waiting for a comment first.

3. **Wait for assignment.** A maintainer will assign the issue when appropriate, whether or not a comment was left. Please wait for this before investing significant time in implementation, as priorities and approaches can shift.

4. **Create a branch and implement.** Once assigned, fork the repository (if you haven't already), create a dedicated branch, and begin your work.

   ```bash
   git checkout -b fix/short-description   # or feature/short-description
   ```

5. **Open a focused PR and link the issue.** When you're ready, open a pull request and reference the issue in the description (e.g., `Closes #123`). Keep the PR scoped to the work described in the issue.

> **Why this matters:** Assignment (with or without a comment) helps maintainers track who is working on what and prevent two contributors from solving the same problem independently. It also gives you a chance to align on the expected approach before writing code.

Not sure where to start? Try a [`good first issue`](https://github.com/semantica-agi/semantica/labels/good%20first%20issue) or ask in [Discord](https://discord.gg/sV34vps5hH).

---

## 🔀 Duplicate PRs & Issue Priority

When more than one pull request targets the same issue, maintainers triage using this order of priority. These rules decide between PRs that are otherwise following the [assignment workflow above](#-working-on-an-existing-issue) — opening a PR before being assigned doesn't grant priority on its own, and an unassigned PR can still be closed as a duplicate once someone else is assigned to the issue.

1. **Contributor-raised issue with an existing PR.** If the person who opened the issue has also opened a PR for it, that PR is prioritized (they still need to be assigned before it's merged).
2. **Maintainer-raised issue with a claim comment.** If we opened the issue and someone has commented asking to work on it, we assign it to them and check their PR before picking up any other PR for the same issue.
3. **No prior assignment or comment.** If multiple PRs exist and no one was assigned or claimed the issue first, priority goes to whichever contributor has the most consistent activity in the repo over the last 60 days (e.g., merged PRs, substantive reviews, or issue triage participation) — not just PR volume.
4. **Late duplicate PRs.** If a PR is opened after another contributor has already been assigned to the issue, we close the duplicate early rather than let it sit open, and point the author to another open issue (or ask them to check `main` for newly opened ones). This avoids contributors spending time updating a PR that won't be merged.
5. **Overlapping scope.** If a PR covers multiple issues, or there's genuine overlap between competing PRs, maintainers discuss it on [Discord](https://discord.gg/sV34vps5hH) before deciding rather than resolving it unilaterally.

**Why this matters:** it keeps triage predictable, avoids wasted contributor effort on PRs that won't merge, and helps retain active contributors.

---

## 🎯 Ways to Contribute

### 💻 Code

**What you can do:**
- Fix bugs
- Add new features
- Improve code quality (add type hints, docstrings, improve error messages)
- Optimize performance

**Where:** `semantica/` directory

**Good first issues:** Add docstrings, type hints, or improve error messages

---

### 📝 Documentation

**What you can do:**
- Fix typos and grammar errors
- Improve clarity and readability
- Add code examples and tutorials
- Create new cookbook notebooks
- Improve API documentation (docstrings)
- Create troubleshooting guides
- Update installation instructions
- Add missing documentation

**Where:** `README.md`, `docs/`, `cookbook/`, docstrings in code

**Good first issues:** Fix typos, add examples, create cookbook tutorials, improve docstrings

**Documentation formatting:**
- Use clear, concise language
- Include code examples where helpful
- Follow markdown best practices
- Use proper headings hierarchy
- Add links to related sections
- Include screenshots for UI-related docs

---

### 🧪 Testing

**What you can do:**
- Add unit tests
- Improve test coverage
- Add integration tests

**Where:** `tests/` directory

**Good first issues:** Add tests for specific functions or classes

---

### 🐛 Bug Reports

**What:** Report bugs you find

**How:** Use the [bug report template](https://github.com/semantica-agi/semantica/issues/new?template=bug_report.md)

**Include:** Description, steps to reproduce, expected vs actual behavior, environment details

---

### 💡 Feature Requests

**What:** Suggest new features or improvements

**How:** Use the [feature request template](https://github.com/semantica-agi/semantica/issues/new?template=feature_request.md)

**Include:** Problem statement, proposed solution, use cases

---

### 🎨 Cookbook & Examples

**What:** Create tutorials and examples

**Where:** `cookbook/` directory

**Examples:** Create new notebooks, add examples, improve existing tutorials

---

### 💬 Community Support

**What:** Help others in the community

**Where:** [Discord](https://discord.gg/sV34vps5hH), [GitHub Discussions](https://github.com/semantica-agi/semantica/discussions)

**Examples:** Answer questions, review PRs, share your projects

---

### 🎓 Educational Content

**What:** Create educational materials

**Examples:** Blog posts, video tutorials, talks, workshops, case studies

---

### 🔧 Other Contributions

- **Design & Graphics:** Logos, diagrams, visualizations
- **Tools & Integrations:** CLI tools, integrations with other frameworks
- **Infrastructure:** CI/CD improvements, Docker optimization
- **Security:** Report security vulnerabilities (privately)

---

## 📋 Getting Started

### 1. Fork & Clone

First, [fork Semantica](https://github.com/semantica-agi/semantica/fork) on GitHub, then:

```bash
git clone https://github.com/your-username/semantica.git
cd semantica
git remote add upstream https://github.com/semantica-agi/semantica.git
```

### 2. Set Up Environment

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dev dependencies
pip install -e ".[dev]"

# Install pre-commit hooks (optional)
pre-commit install
```

### Pinned CI dependencies

`requirements-ci.txt` pins every transitive dependency at exact versions so CI,
security scans, and release builds install the same packages every run (the
Python equivalent of `explorer/package-lock.json` + `npm ci`). It is a
**separate build environment**: every package carries a SHA-256 hash
(`--generate-hashes`), so installs are reproducible and supply-chain safe —
never install into your local dev environment from it.

Regenerate it after changing `pyproject.toml` dependencies:

```bash
pip install uv==0.12.1
uv pip compile pyproject.toml --python-version 3.11 --extra all --generate-hashes -o requirements-ci.txt
```

The `all` extra is the repo's cross-platform dependency set (GPU extras like
`faiss-gpu`/`cupy` are excluded and installed separately on Linux — see
`pyproject.toml`). Keep the pinned `uv` version in sync with CI so regeneration
is deterministic.

CI's staleness check re-resolves with the committed lockfile as a constraint
and compares version lines only: upstream package releases never fail CI —
the lockfile changes only when `pyproject.toml` changes intentionally.

CI fails if `requirements-ci.txt` is stale relative to `pyproject.toml`
(the version-line comparison detects new/removed/changed dependencies).

Build-system pins: `[build-system].requires` is pinned to exact versions
(`setuptools==84.0.0`, `wheel==0.48.0`) and release builds run
`python -m build --no-isolation` against the lockfile — no unpinned
build-time isolation anywhere.

### 3. Create Branch

```bash
git checkout -b feature/your-feature-name
# or
git checkout -b fix/bug-description
```

### 4. Make Changes

- Follow code style (see below)
- Add tests for new features
- Update documentation

### 5. Run Checks

```bash
pytest                          # Run tests
black semantica/ tests/        # Format code
isort semantica/ tests/         # Sort imports
flake8 semantica/ tests/        # Lint
```

Or use pre-commit hooks: `pre-commit run --all-files`

### 6. Commit & Push

```bash
git commit -m "feat(module): add new feature"
git push origin feature/your-feature-name
```

Then create a pull request on GitHub!

---

## 📐 Code Style

We use automated tools:

| Tool     | Purpose                    | Command                    |
|----------|----------------------------|----------------------------|
| **Black** | Code formatting            | `black semantica/ tests/` |
| **isort** | Import sorting             | `isort semantica/ tests/` |
| **flake8** | Style enforcement          | `flake8 semantica/ tests/` |
| **mypy** | Type checking              | `mypy semantica/`          |

**Run all:** `black semantica/ tests/ && isort semantica/ tests/ && flake8 semantica/ tests/ && mypy semantica/`

---

## 🧪 Testing

```bash
pytest                          # Run all tests
pytest --cov=semantica         # With coverage
pytest tests/test_file.py      # Specific file
```

**Coverage goal:** 80% minimum, 90%+ for critical modules

---

## 📝 Commit Messages

Use [Conventional Commits](https://www.conventionalcommits.org/):

```
feat(kg): add temporal graph support
fix(parse): handle empty PDF files
docs(readme): add installation guide
test(extract): add unit tests
```

**Types:** `feat`, `fix`, `docs`, `test`, `refactor`, `perf`, `style`, `chore`

---

## ✅ PR Checklist

Before submitting:

- [ ] Code follows style guidelines
- [ ] Tests pass locally
- [ ] New tests added (if applicable)
- [ ] Documentation updated
- [ ] Commit messages follow conventions
- [ ] No merge conflicts

---

## 📖 Documentation Standards

### Code Documentation (Docstrings)

**Format:** Use Google-style docstrings

```python
def extract_entities(text: str, model: str = "transformer") -> List[Entity]:
    """Extract named entities from text.
    
    Args:
        text: Input text to process
        model: NER model to use (default: "transformer")
    
    Returns:
        List of extracted Entity objects
    
    Raises:
        ValueError: If text is empty or model is invalid
    
    Example:
        >>> from semantica.semantic_extract import NERExtractor
        >>> ner = NERExtractor(method="ml", model="en_core_web_sm")
        >>> entities = ner.extract("Apple Inc. was founded in 1976.")
        >>> len(entities)
        2
    """
```

### Markdown Documentation Formatting

**General Guidelines:**
- Use clear headings (H1 for title, H2 for main sections, H3 for subsections)
- Keep paragraphs short and focused
- Use bullet points for lists
- Add code blocks with syntax highlighting
- Include links to related documentation

**Code Blocks:**
- Use triple backticks with language identifier: ` ```python `, ` ```bash `
- Include comments in code examples
- Show expected output when helpful

**Examples:**

```markdown
## Section Title

Brief introduction paragraph.

### Subsection

- Bullet point 1
- Bullet point 2

**Code example:**

```python
from semantica import SomeClass

instance = SomeClass()
result = instance.method()
```

**Note:** Additional context or warnings.
```

**Best Practices:**
- Start with an overview/introduction
- Use consistent terminology
- Include "See also" links
- Add examples for complex concepts
- Keep formatting consistent across docs

---

## 🆘 Getting Help

- 💬 [Discord](https://discord.gg/sV34vps5hH) - Real-time chat
- 💭 [GitHub Discussions](https://github.com/semantica-agi/semantica/discussions) - Q&A
- 🐛 [GitHub Issues](https://github.com/semantica-agi/semantica/issues) - Bug reports

**Before asking:** Check existing documentation, search issues/discussions, review cookbook examples

---

## 🏆 Recognition

All contributors are recognized in:
- [CONTRIBUTORS.md](CONTRIBUTORS.md)
- GitHub contributors page
- Release notes

We follow the [all-contributors](https://allcontributors.org) specification!

---

## 📜 Code of Conduct

This project follows a [Code of Conduct](CODE_OF_CONDUCT.md). Be respectful and inclusive.

---

## 📚 Resources

- [README.md](README.md) - Project overview
- [Cookbook](cookbook/) - Tutorials and examples
- [Documentation](docs/) - Comprehensive guides

---

**Thank you for contributing!** 🚀

Every contribution matters - whether it's a single line of code, a typo fix, a helpful answer, or a bug report. We appreciate you! 🙏

⭐ **Give us a Star** • 🍴 **[Fork Semantica](https://github.com/semantica-agi/semantica/fork)** • 💬 **Join our [Discord](https://discord.gg/sV34vps5hH)**
