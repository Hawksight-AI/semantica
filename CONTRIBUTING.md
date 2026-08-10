# Contributing to Semantica

Thank you for your interest in contributing! Every contribution, no matter how small, is valuable. 🎉

⭐ **Give us a Star** • 🍴 **[Fork Semantica](https://github.com/Hawksight-AI/semantica/fork)** • 💬 **Join our [Discord](https://discord.gg/sV34vps5hH)**

> **New to contributing?** Start with a [`good first issue`](https://github.com/Hawksight-AI/semantica/labels/good%20first%20issue) or join our [Discord](https://discord.gg/sV34vps5hH) community.

---

## 🚀 Quick Start

1. Find a [`good first issue`](https://github.com/Hawksight-AI/semantica/labels/good%20first%20issue)
2. [Fork Semantica](https://github.com/Hawksight-AI/semantica/fork) & clone the repository
3. Make your changes
4. Submit a pull request!

**Need help?** Join [Discord](https://discord.gg/sV34vps5hH) or [GitHub Discussions](https://github.com/Hawksight-AI/semantica/discussions)

---

## 🗂️ Working on an Existing Issue

If you want to work on an open GitHub issue, please follow these steps to keep things coordinated and avoid duplicate effort:

1. **Check the issue.** Look at the issue's assignees and recent comments. If someone is already actively working on it, consider a different issue or ask in the comments whether help is welcome.

2. **Comment before you start.** Leave a comment on the issue saying you'd like to work on it — something like *"I'd like to take this on"* is enough. This gives maintainers the context they need to assign the issue appropriately.

3. **Wait for assignment.** A maintainer will review the request and assign the issue when appropriate. Please wait for this before investing significant time in implementation, as priorities and approaches can shift.

4. **Create a branch and implement.** Once assigned, fork the repository (if you haven't already), create a dedicated branch, and begin your work.

   ```bash
   git checkout -b fix/short-description   # or feature/short-description
   ```

5. **Open a focused PR and link the issue.** When you're ready, open a pull request and reference the issue in the description (e.g., `Closes #123`). Keep the PR scoped to the work described in the issue.

> **Why this matters:** Commenting before opening a PR helps maintainers track who is working on what, assign issues correctly, and prevent two contributors from solving the same problem independently. It also gives you a chance to align on the expected approach before writing code.

Not sure where to start? Try a [`good first issue`](https://github.com/Hawksight-AI/semantica/labels/good%20first%20issue) or ask in [Discord](https://discord.gg/sV34vps5hH).

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

**How:** Use the [bug report template](https://github.com/Hawksight-AI/semantica/issues/new?template=bug_report.md)

**Include:** Description, steps to reproduce, expected vs actual behavior, environment details

---

### 💡 Feature Requests

**What:** Suggest new features or improvements

**How:** Use the [feature request template](https://github.com/Hawksight-AI/semantica/issues/new?template=feature_request.md)

**Include:** Problem statement, proposed solution, use cases

---

### 🎨 Cookbook & Examples

**What:** Create tutorials and examples

**Where:** `cookbook/` directory

**Examples:** Create new notebooks, add examples, improve existing tutorials

---

### 💬 Community Support

**What:** Help others in the community

**Where:** [Discord](https://discord.gg/sV34vps5hH), [GitHub Discussions](https://github.com/Hawksight-AI/semantica/discussions)

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

First, [fork Semantica](https://github.com/Hawksight-AI/semantica/fork) on GitHub, then:

```bash
git clone https://github.com/your-username/semantica.git
cd semantica
git remote add upstream https://github.com/Hawksight-AI/semantica.git
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
- 💭 [GitHub Discussions](https://github.com/Hawksight-AI/semantica/discussions) - Q&A
- 🐛 [GitHub Issues](https://github.com/Hawksight-AI/semantica/issues) - Bug reports

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

⭐ **Give us a Star** • 🍴 **[Fork Semantica](https://github.com/Hawksight-AI/semantica/fork)** • 💬 **Join our [Discord](https://discord.gg/sV34vps5hH)**
