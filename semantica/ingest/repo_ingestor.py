"""
Repository Ingestion Module

This module provides comprehensive Git repository ingestion capabilities for the
Semantica framework, enabling repository cloning, code analysis, and commit
history processing.

Key Features:
    - Git repository cloning and analysis
    - Code file extraction with language detection
    - Commit history processing and analysis
    - Branch and tag analysis
    - Code structure analysis (classes, functions, imports)
    - Dependency analysis
    - Documentation extraction

Main Classes:
    - RepoIngestor: Main repository ingestion class
    - GitAnalyzer: Git repository analyzer
    - CodeExtractor: Code content extractor

Example Usage:
    >>> from semantica.ingest import RepoIngestor
    >>> ingestor = RepoIngestor()
    >>> repo_data = ingestor.ingest_repository("https://github.com/user/repo.git")
    >>> commits = ingestor.analyze_commits(repo_path, max_commits=100)

Author: Semantica Contributors
License: MIT
"""

import ipaddress
import os
import re
import shutil
import socket
import tempfile
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union
from urllib.parse import urlparse

import git

from ..utils.exceptions import ProcessingError, ValidationError
from ..utils.logging import get_logger
from ..utils.progress_tracker import get_progress_tracker

# Safe subset of GitPython clone_from kwargs. Broader kwargs (multi_options,
# upload_pack, template, config, env, …) have been used in denylist-bypass
# attacks against older GitPython releases — keep them out of the call surface.
ALLOWED_CLONE_OPTIONS: Set[str] = {"depth", "branch", "single_branch", "no_tags"}
ALLOWED_REPO_URL_SCHEMES = frozenset({"https", "http", "git", "ssh"})
# SCP-like SSH remotes: user@host:path/to/repo.git (no scheme)
_SCP_LIKE_REPO_URL_RE = re.compile(r"^[^@\s]+@[^:\s]+:.+$")
_ENV_VAR_TOKEN_RE = re.compile(
    r"\$(\{[A-Za-z_][A-Za-z0-9_]*\}|[A-Za-z_][A-Za-z0-9_]*)"
)
# Short-lived DNS cache for host validation. This reduces repeated lookups but
# does not eliminate DNS-rebinding / TOCTOU races between validate and clone —
# network egress controls remain recommended.
_REPO_HOST_RESOLVE_CACHE: "OrderedDict[str, Tuple[float, Tuple[str, ...]]]" = (
    OrderedDict()
)
_REPO_HOST_RESOLVE_CACHE_TTL_SECONDS = 60.0
_REPO_HOST_RESOLVE_CACHE_MAX_ENTRIES = 1024
# Guards all reads/writes/prunes of _REPO_HOST_RESOLVE_CACHE. The cache is a
# module-level OrderedDict shared by every RepoIngestor instance and every
# thread; without a lock, concurrent ingest_repository() calls can mutate the
# dict while another thread is iterating it (e.g. during pruning), raising
# "RuntimeError: OrderedDict mutated during iteration". The blocking
# socket.getaddrinfo() call is intentionally kept outside this lock so a slow
# DNS lookup for one host cannot stall cache access for other hosts.
_REPO_HOST_RESOLVE_CACHE_LOCK = threading.Lock()


@dataclass
class CodeFile:
    """
    Code file representation.

    This dataclass represents a code file with its content, metadata, and
    structural information.

    Attributes:
        path: File path relative to repository root
        name: File name
        language: Detected programming language
        content: File content as string
        size: File size in bytes
        lines: Number of lines in file
        metadata: Additional metadata (extension, modification date, structure)
    """

    path: str
    name: str
    language: str
    content: str
    size: int
    lines: int
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CommitInfo:
    """
    Commit information representation.

    This dataclass represents a Git commit with its metadata and statistics.

    Attributes:
        hash: Commit hash (short form)
        message: Commit message
        author: Commit author
        date: Commit date
        files_changed: List of files changed in commit
        additions: Number of lines added
        deletions: Number of lines deleted
    """

    hash: str
    message: str
    author: str
    date: datetime
    files_changed: List[str] = field(default_factory=list)
    additions: int = 0
    deletions: int = 0


class CodeExtractor:
    """
    Code content extraction and processing.

    This class extracts code content from various file types, detects
    programming languages, extracts structure (classes, functions), and
    analyzes dependencies.

    Example Usage:
        >>> extractor = CodeExtractor()
        >>> code_file = extractor.extract_file_content(Path("file.py"))
        >>> docs = extractor.extract_documentation(Path("file.py"))
        >>> deps = extractor.analyze_dependencies(Path("file.py"))
    """

    # File extension to language mapping
    LANGUAGE_MAP = {
        ".py": "python",
        ".js": "javascript",
        ".ts": "typescript",
        ".java": "java",
        ".cpp": "cpp",
        ".c": "c",
        ".cs": "csharp",
        ".go": "go",
        ".rs": "rust",
        ".rb": "ruby",
        ".php": "php",
        ".swift": "swift",
        ".kt": "kotlin",
        ".scala": "scala",
        ".r": "r",
        ".m": "matlab",
        ".sh": "shell",
        ".sql": "sql",
        ".html": "html",
        ".css": "css",
        ".scss": "scss",
        ".json": "json",
        ".xml": "xml",
        ".yaml": "yaml",
        ".yml": "yaml",
        ".md": "markdown",
        ".txt": "text",
    }

    def __init__(self, **config):
        """
        Initialize code extractor.

        Args:
            **config: Extraction configuration
        """
        self.logger = get_logger("code_extractor")
        self.config = config

    def extract_file_content(
        self, file_path: Path, language: Optional[str] = None
    ) -> CodeFile:
        """
        Extract content from code file.

        Args:
            file_path: Path to code file
            language: Programming language (auto-detected if not provided)

        Returns:
            CodeFile: Extracted code file data
        """
        if not file_path.exists():
            raise ValidationError(f"File not found: {file_path}")

        # Detect language if not provided
        if language is None:
            language = self._detect_language(file_path)

        # Read file content
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
        except Exception as e:
            self.logger.warning(f"Failed to read file {file_path}: {e}")
            content = ""

        # Get file stats
        stat = file_path.stat()
        lines = content.count("\n") + (1 if content else 0)

        # Extract metadata
        metadata = {
            "extension": file_path.suffix,
            "size_bytes": stat.st_size,
            "modified": datetime.fromtimestamp(stat.st_mtime),
        }

        # Extract structure if supported
        if language in ["python", "javascript", "typescript", "java"]:
            metadata["structure"] = self._extract_structure(content, language)

        return CodeFile(
            path=str(file_path),
            name=file_path.name,
            language=language,
            content=content,
            size=stat.st_size,
            lines=lines,
            metadata=metadata,
        )

    def extract_documentation(self, file_path: Path) -> Dict[str, Any]:
        """
        Extract documentation from code file.

        Args:
            file_path: Path to code file

        Returns:
            dict: Documentation content
        """
        language = self._detect_language(file_path)
        docs = {"docstrings": [], "comments": [], "readme": None}

        if file_path.name.lower() in ["readme.md", "readme.txt", "readme"]:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                docs["readme"] = f.read()
            return docs

        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
        except Exception:
            return docs

        # Extract docstrings (Python style)
        if language == "python":
            docstring_pattern = r'"""(.*?)"""'
            matches = re.findall(docstring_pattern, content, re.DOTALL)
            docs["docstrings"] = [m.strip() for m in matches]

        # Extract comments
        comment_patterns = {
            "python": r"#\s*(.*)",
            "javascript": r"//\s*(.*)",
            "java": r"//\s*(.*)",
            "c": r"//\s*(.*)",
            "cpp": r"//\s*(.*)",
        }

        if language in comment_patterns:
            pattern = comment_patterns[language]
            matches = re.findall(pattern, content, re.MULTILINE)
            docs["comments"] = [m.strip() for m in matches if m.strip()]

        return docs

    def analyze_dependencies(self, file_path: Path) -> Dict[str, Any]:
        """
        Analyze file dependencies and imports.

        Args:
            file_path: Path to code file

        Returns:
            dict: Dependency analysis
        """
        language = self._detect_language(file_path)
        dependencies = {"external": [], "internal": [], "language": language}

        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
        except Exception:
            return dependencies

        # Python imports
        if language == "python":
            import_pattern = r"^(?:from|import)\s+([\w.]+)"
            matches = re.findall(import_pattern, content, re.MULTILINE)
            dependencies["external"] = matches

        # JavaScript/TypeScript imports
        elif language in ["javascript", "typescript"]:
            import_pattern = r"(?:import|require)\(?['\"]([^'\"]+)['\"]"
            matches = re.findall(import_pattern, content)
            dependencies["external"] = matches

        # Java imports
        elif language == "java":
            import_pattern = r"^import\s+([\w.]+)"
            matches = re.findall(import_pattern, content, re.MULTILINE)
            dependencies["external"] = matches

        return dependencies

    def _detect_language(self, file_path: Path) -> str:
        """Detect programming language from file extension."""
        ext = file_path.suffix.lower()
        return self.LANGUAGE_MAP.get(ext, "unknown")

    def _extract_structure(self, content: str, language: str) -> Dict[str, Any]:
        """Extract code structure (functions, classes, etc.)."""
        structure = {"classes": [], "functions": [], "imports": []}

        if language == "python":
            # Extract classes
            class_pattern = r"^class\s+(\w+)"
            structure["classes"] = re.findall(class_pattern, content, re.MULTILINE)

            # Extract functions
            func_pattern = r"^\s*def\s+(\w+)"
            structure["functions"] = re.findall(func_pattern, content, re.MULTILINE)

        elif language in ["javascript", "typescript"]:
            # Extract classes
            class_pattern = r"class\s+(\w+)"
            structure["classes"] = re.findall(class_pattern, content)

            # Extract functions
            func_pattern = r"function\s+(\w+)|const\s+(\w+)\s*=\s*(?:async\s+)?\(|(\w+)\s*:\s*(?:async\s+)?\(.*?\)\s*=>"
            matches = re.findall(func_pattern, content)
            structure["functions"] = [m[0] or m[1] or m[2] for m in matches if any(m)]

        return structure


class GitAnalyzer:
    """
    Git repository analysis and statistics.

    This class analyzes repository structure and history, calculates code
    metrics and statistics, and detects code patterns.

    Example Usage:
        >>> analyzer = GitAnalyzer()
        >>> structure = analyzer.analyze_structure(repo_path)
        >>> metrics = analyzer.calculate_metrics(repo_path)
    """

    def __init__(self, **config):
        """
        Initialize Git analyzer.

        Sets up the analyzer with configuration options.

        Args:
            **config: Analyzer configuration options (currently unused)
        """
        self.logger = get_logger("git_analyzer")
        self.config = config

    def analyze_structure(self, repo_path: Path) -> Dict[str, Any]:
        """
        Analyze repository file structure.

        Args:
            repo_path: Path to repository

        Returns:
            dict: Structure analysis results
        """
        structure = {
            "total_files": 0,
            "total_directories": 0,
            "file_types": {},
            "directory_structure": {},
            "max_depth": 0,
        }

        def analyze_dir(path: Path, depth: int = 0):
            structure["max_depth"] = max(structure["max_depth"], depth)

            try:
                items = list(path.iterdir())
                for item in items:
                    if item.is_file():
                        structure["total_files"] += 1
                        ext = item.suffix.lower() or "no_extension"
                        structure["file_types"][ext] = (
                            structure["file_types"].get(ext, 0) + 1
                        )
                    elif item.is_dir() and item.name not in [
                        ".git",
                        "__pycache__",
                        "node_modules",
                    ]:
                        structure["total_directories"] += 1
                        analyze_dir(item, depth + 1)
            except PermissionError:
                pass

        analyze_dir(repo_path)
        return structure

    def calculate_metrics(self, repo_path: Path) -> Dict[str, Any]:
        """
        Calculate repository metrics and statistics.

        Args:
            repo_path: Path to repository

        Returns:
            dict: Metrics dictionary
        """
        metrics = {
            "total_lines": 0,
            "total_files": 0,
            "lines_by_language": {},
            "files_by_language": {},
        }

        extractor = CodeExtractor()

        for file_path in repo_path.rglob("*"):
            if file_path.is_file() and file_path.name not in [".gitignore", ".gitkeep"]:
                try:
                    code_file = extractor.extract_file_content(file_path)
                    metrics["total_files"] += 1
                    metrics["total_lines"] += code_file.lines

                    lang = code_file.language
                    metrics["lines_by_language"][lang] = (
                        metrics["lines_by_language"].get(lang, 0) + code_file.lines
                    )
                    metrics["files_by_language"][lang] = (
                        metrics["files_by_language"].get(lang, 0) + 1
                    )
                except Exception:
                    continue

        return metrics

    def detect_patterns(self, repo_path: Path) -> Dict[str, Any]:
        """
        Detect code patterns and conventions.

        Args:
            repo_path: Path to repository

        Returns:
            dict: Pattern analysis results
        """
        patterns = {
            "naming_conventions": {},
            "file_organization": {},
            "common_structures": [],
        }

        # Analyze naming patterns
        python_files = list(repo_path.rglob("*.py"))
        if python_files:
            patterns["naming_conventions"]["python"] = "detected"

        return patterns


class RepoIngestor:
    """
    Git repository ingestion handler.

    This class provides comprehensive Git repository ingestion capabilities,
    cloning repositories, extracting code files and documentation, and
    processing commit history and metadata.

    Features:
        - Repository cloning from various platforms
        - Code file extraction with filtering
        - Commit history analysis
        - Repository structure and metrics analysis
        - Branch and tag information

    Example Usage:
        >>> ingestor = RepoIngestor()
        >>> repo_data = ingestor.ingest_repository(
        ...     "https://github.com/user/repo.git",
        ...     branch="main",
        ...     include_history=True
        ... )
        >>> ingestor.cleanup()
    """

    SUPPORTED_PLATFORMS = ["github", "gitlab", "bitbucket", "generic"]

    def __init__(self, config: Optional[Dict[str, Any]] = None, **kwargs):
        """
        Initialize repository ingestor.

        Sets up the ingestor with code extractor and analyzer. Note that
        the `git` library must be installed for this module to work.

        Args:
            config: Optional repository ingestion configuration dictionary
            **kwargs: Additional configuration parameters (merged into config)
        """
        self.logger = get_logger("repo_ingestor")
        self.config = config or {}
        self.config.update(kwargs)

        # Initialize code extractor
        self.code_extractor = CodeExtractor(**self.config)

        # Initialize analyzer
        self.analyzer = GitAnalyzer(**self.config)

        # Initialize progress tracker
        self.progress_tracker = get_progress_tracker()

        # Temporary directory for cloning
        self.temp_dir = None

        self.logger.debug("Repo ingestor initialized")

    @staticmethod
    def _is_scp_like_repo_url(repo_url: str) -> bool:
        """Return True for scp-like SSH remotes (``user@host:path``)."""
        url = repo_url.strip()
        # Avoid treating scheme URLs with userinfo as scp-like (e.g. https://u@h/...)
        if "://" in url:
            return False
        return bool(_SCP_LIKE_REPO_URL_RE.match(url))

    @staticmethod
    def _scp_like_host(repo_url: str) -> str:
        """Extract the hostname from an scp-like remote (``user@host:path``)."""
        _, rest = repo_url.strip().split("@", 1)
        host, _ = rest.split(":", 1)
        return host

    @staticmethod
    def _normalize_repo_url(repo_url: str) -> str:
        """Normalize scp-like remotes to ``ssh://`` URLs; leave others unchanged.

        ``git@host:org/repo.git`` → ``ssh://git@host/org/repo.git``
        """
        url = repo_url.strip()
        if not RepoIngestor._is_scp_like_repo_url(url):
            return url
        user_host, path = url.split(":", 1)
        if not path.startswith("/"):
            path = f"/{path}"
        return f"ssh://{user_host}{path}"

    @staticmethod
    def _is_blocked_ip(
        ip: Union[ipaddress.IPv4Address, ipaddress.IPv6Address],
    ) -> bool:
        """Return True if *ip* is an SSRF-sensitive address.

        Blocks private (RFC1918/ULA), loopback, link-local (including
        169.254.x.x / fe80::/10 cloud-metadata ranges), and unspecified
        addresses.

        Intentionally does **not** use ``ip.is_reserved``: Python's
        ``ipaddress`` module marks the NAT64 Well-Known Prefix
        (64:ff9b::/96, RFC 6052) as reserved, which causes false positives
        on IPv6-only and dual-stack networks that use NAT64 for public
        Internet access (e.g., github.com resolves to 64:ff9b::… on such
        networks). Those addresses are not SSRF-sensitive.
        """
        return bool(
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_unspecified
        )

    @staticmethod
    def _resolve_repo_host_ips(host: str) -> Tuple[str, ...]:
        """Resolve *host* to IP strings via ``socket.getaddrinfo``, with TTL cache.

        Note: caching and pre-clone resolution mitigate repeated lookups but
        cannot fully prevent DNS rebinding between validation and clone.
        Prefer network-layer egress controls for defense in depth.
        """
        cache_key = host.lower().rstrip(".")
        now = time.monotonic()
        with _REPO_HOST_RESOLVE_CACHE_LOCK:
            RepoIngestor._prune_repo_host_resolve_cache_locked(now)
            cached = _REPO_HOST_RESOLVE_CACHE.get(cache_key)
            if cached is not None:
                expires_at, ips = cached
                if now < expires_at:
                    _REPO_HOST_RESOLVE_CACHE.move_to_end(cache_key)
                    return ips
                _REPO_HOST_RESOLVE_CACHE.pop(cache_key, None)

        # DNS resolution is blocking I/O; keep it outside the lock so a slow
        # or hanging lookup for one host cannot stall cache access for
        # concurrent lookups of other hosts.
        try:
            addrinfos = socket.getaddrinfo(
                host, None, type=socket.SOCK_STREAM
            )
        except socket.gaierror as exc:
            raise ValidationError(
                f"Cannot resolve repository host {host!r}: {exc}"
            ) from exc

        ips: List[str] = []
        seen: Set[str] = set()
        for _family, _type, _proto, _canonname, sockaddr in addrinfos:
            addr = sockaddr[0]
            if addr not in seen:
                seen.add(addr)
                ips.append(addr)

        if not ips:
            raise ValidationError(
                f"Cannot resolve repository host {host!r}: no addresses"
            )

        result = tuple(ips)
        with _REPO_HOST_RESOLVE_CACHE_LOCK:
            now = time.monotonic()
            _REPO_HOST_RESOLVE_CACHE[cache_key] = (
                now + _REPO_HOST_RESOLVE_CACHE_TTL_SECONDS,
                result,
            )
            _REPO_HOST_RESOLVE_CACHE.move_to_end(cache_key)
            RepoIngestor._prune_repo_host_resolve_cache_locked(now)
        return result

    @staticmethod
    def _prune_repo_host_resolve_cache(now: Optional[float] = None) -> None:
        """Remove expired host entries and enforce a hard cache size cap.

        Acquires ``_REPO_HOST_RESOLVE_CACHE_LOCK``. Callers that already hold
        the lock must use ``_prune_repo_host_resolve_cache_locked`` instead to
        avoid deadlocking on the (non-reentrant) lock.
        """
        if now is None:
            now = time.monotonic()
        with _REPO_HOST_RESOLVE_CACHE_LOCK:
            RepoIngestor._prune_repo_host_resolve_cache_locked(now)

    @staticmethod
    def _prune_repo_host_resolve_cache_locked(now: Optional[float] = None) -> None:
        """Prune implementation; caller must already hold the cache lock."""
        if now is None:
            now = time.monotonic()

        expired_keys = [
            cache_key
            for cache_key, (expires_at, _ips) in _REPO_HOST_RESOLVE_CACHE.items()
            if expires_at <= now
        ]
        for cache_key in expired_keys:
            _REPO_HOST_RESOLVE_CACHE.pop(cache_key, None)

        while len(_REPO_HOST_RESOLVE_CACHE) > _REPO_HOST_RESOLVE_CACHE_MAX_ENTRIES:
            _REPO_HOST_RESOLVE_CACHE.popitem(last=False)

    @staticmethod
    def _validate_repo_host(host: str) -> None:
        """Reject localhost names and hosts resolving to blocked addresses.

        Literal IPs are checked directly. Hostnames are resolved with
        ``socket.getaddrinfo`` and **every** returned address is screened.
        """
        if not host:
            raise ValidationError("Repository URL must include a host")

        lowered = host.lower().rstrip(".")
        if lowered == "localhost" or lowered.endswith(".localhost"):
            raise ValidationError(f"Repository host is not allowed: {host}")

        try:
            ip = ipaddress.ip_address(host)
        except ValueError:
            # Hostname: resolve and validate all returned addresses
            for addr in RepoIngestor._resolve_repo_host_ips(host):
                try:
                    resolved = ipaddress.ip_address(addr)
                except ValueError:
                    continue
                if RepoIngestor._is_blocked_ip(resolved):
                    raise ValidationError(
                        f"Repository host resolves to a blocked address: "
                        f"{host} -> {addr}"
                    )
            return

        if RepoIngestor._is_blocked_ip(ip):
            raise ValidationError(
                f"Repository host resolves to a blocked address: {host}"
            )

    @staticmethod
    def _is_local_repo_path(repo_url: str) -> bool:
        """Return True if *repo_url* looks like a local filesystem path.

        Matches absolute paths (``/…``, ``C:\\…``), relative paths
        (``./…``, ``../…``), and bare names without a scheme or ``@host:``
        pattern that would be interpreted as a local path by git.
        """
        url = repo_url.strip()
        if "://" in url:
            return False
        if RepoIngestor._is_scp_like_repo_url(url):
            return False
        # Absolute POSIX or Windows paths, or relative paths
        p = Path(url)
        if p.is_absolute():
            return True
        # ./  or ../
        if url.startswith(("./", "../", ".\\", "..\\")):
            return True
        # Existing local directory (best-effort; may not exist yet during tests)
        if p.exists():
            return True
        return False

    @staticmethod
    def _validate_repo_url(repo_url: str) -> None:
        """Validate a repository URL before cloning.

        Accepts http(s)/git/ssh URLs, scp-like SSH remotes
        (``user@host:path``), and local filesystem paths.  Rejects empty
        values, unsupported schemes, missing hosts, environment variable
        expansion tokens (``$VAR`` / ``${VAR}``), and hosts that are or
        resolve to private / loopback / link-local addresses.

        Local filesystem paths bypass network validation because
        ``git clone /path/to/local/repo`` makes no network requests and
        carries no SSRF risk.

        DNS resolution is TOCTOU-sensitive (rebinding); pair with egress
        controls in production deployments.
        """
        if not isinstance(repo_url, str) or not repo_url.strip():
            raise ValidationError("Repository URL must be a non-empty string")

        # Defense-in-depth against GitPython env-var expansion in clone URLs
        # (GHSA-2f96-g7mh-g2hx / related). Prefer rejecting before clone_from.
        if _ENV_VAR_TOKEN_RE.search(repo_url):
            raise ValidationError(
                "Repository URL must not contain environment variable "
                "references ($VAR / ${VAR})"
            )

        url = repo_url.strip()

        # Local filesystem paths: no network, no SSRF risk — skip host checks.
        if RepoIngestor._is_local_repo_path(url):
            return

        # scp-like syntax has no URL scheme; validate host then accept.
        if RepoIngestor._is_scp_like_repo_url(url):
            RepoIngestor._validate_repo_host(RepoIngestor._scp_like_host(url))
            return

        try:
            parsed = urlparse(url)
            # ``hostname`` can raise ValueError for malformed netloc (e.g. bad IPv6)
            host = parsed.hostname
        except ValueError as e:
            raise ValidationError(f"Invalid repository URL: {e}") from e

        scheme = (parsed.scheme or "").lower()
        if scheme not in ALLOWED_REPO_URL_SCHEMES:
            raise ValidationError(
                f"Unsupported repository URL scheme {scheme!r}. "
                f"Allowed schemes: {sorted(ALLOWED_REPO_URL_SCHEMES)}"
            )
        if not parsed.netloc or not host:
            raise ValidationError(
                f"Repository URL must include a host: {repo_url}"
            )

        RepoIngestor._validate_repo_host(host)

    @staticmethod
    def _filter_clone_options(options: Dict[str, Any]) -> Dict[str, Any]:
        """Return only allowlisted git clone kwargs; reject anything else."""
        # Semantica processing options — never forwarded to clone_from
        non_git_options = {
            "include_history",
            "file_filters",
            "commit_filters",
            "include_extensions",
            "max_depth",
        }
        candidate = {
            k: v for k, v in options.items() if k not in non_git_options
        }
        unsafe = set(candidate) - ALLOWED_CLONE_OPTIONS
        if unsafe:
            raise ValidationError(
                f"Clone option(s) not permitted: {sorted(unsafe)}. "
                f"Allowed options: {sorted(ALLOWED_CLONE_OPTIONS)}"
            )
        return candidate

    def ingest_repository(self, repo_url: str, **options) -> Dict[str, Any]:
        """
        Ingest and process a Git repository.

        Args:
            repo_url: Repository URL
            **options: Processing options:
                - branch: Specific branch to checkout
                - depth: Clone depth (for shallow clones)
                - single_branch: Clone only a single branch
                - no_tags: Skip cloning tags
                - include_history: Whether to include commit history
                - include_extensions: List of file extensions to include (e.g., ["py", "md"])

        Returns:
            dict: Processed repository data
        """
        # Track repository ingestion
        tracking_id = self.progress_tracker.start_tracking(
            file=repo_url,
            module="ingest",
            submodule="RepoIngestor",
            message=f"Repository: {repo_url}",
        )

        try:
            # Validate repository URL before any clone attempt
            self._validate_repo_url(repo_url)
            clone_url = self._normalize_repo_url(repo_url)

            # Handle option aliases and filters
            if "max_depth" in options and "depth" not in options:
                options["depth"] = options["max_depth"]

            clone_options = self._filter_clone_options(options)

            try:
                parsed = git.Repo.clone_from(
                    clone_url, self._get_temp_dir(), **clone_options
                )
            except Exception as e:
                self.progress_tracker.update_tracking(
                    tracking_id, status="failed", message=str(e)
                )
                raise ProcessingError(f"Failed to clone repository: {e}") from e

            repo_path = Path(self.temp_dir)
            repo = git.Repo(repo_path)

            self.progress_tracker.update_tracking(
                tracking_id, message="Cloning repository..."
            )

            # Checkout specific branch if requested
            if options.get("branch"):
                try:
                    repo.git.checkout(options["branch"])
                except Exception as e:
                    self.logger.warning(
                        f"Failed to checkout branch {options['branch']}: {e}"
                    )

            # Extract repository information
            repo_info = self.get_repository_info(repo_url, repo)

            # Prepare file filters
            file_filters = options.get("file_filters", {}).copy()
            if "include_extensions" in options:
                # Normalize extensions to include dot prefix
                exts = options["include_extensions"]
                normalized_exts = [
                    e if e.startswith(".") else f".{e}" for e in exts
                ]
                file_filters["extensions"] = normalized_exts

            # Process code files
            self.progress_tracker.update_tracking(
                tracking_id, message="Extracting code files..."
            )
            code_files = self.extract_code_files(repo_path, **file_filters)

            # Analyze commits if requested
            commits = []
            if options.get("include_history", True):
                self.progress_tracker.update_tracking(
                    tracking_id, message="Analyzing commits..."
                )
                commits = self.analyze_commits(
                    repo_path, **options.get("commit_filters", {})
                )

            # Analyze structure
            self.progress_tracker.update_tracking(
                tracking_id, message="Analyzing structure..."
            )
            structure = self.analyzer.analyze_structure(repo_path)
            metrics = self.analyzer.calculate_metrics(repo_path)

            self.progress_tracker.update_tracking(
                tracking_id,
                status="completed",
                message=f"Processed {len(code_files)} files, {len(commits)} commits",
            )
            return {
                "repository_info": repo_info,
                "code_files": [f.__dict__ for f in code_files],
                "commits": [c.__dict__ for c in commits],
                "structure": structure,
                "metrics": metrics,
                "temp_path": str(repo_path),
            }

        except ValidationError as e:
            # Keep validation failures typed for callers; do not wrap as ProcessingError
            self.progress_tracker.update_tracking(
                tracking_id, status="failed", message=str(e)
            )
            raise
        except Exception as e:
            self.progress_tracker.update_tracking(
                tracking_id, status="failed", message=str(e)
            )
            raise

    def analyze_commits(self, repo_path: Path, **filters) -> List[CommitInfo]:
        """
        Analyze commit history and patterns.

        Args:
            repo_path: Path to repository
            **filters: Filtering criteria:
                - since: Date to start from
                - until: Date to end at
                - author: Filter by author
                - max_commits: Maximum number of commits

        Returns:
            list: Commit analysis results
        """
        try:
            repo = git.Repo(repo_path)
        except Exception as e:
            raise ProcessingError(f"Failed to open repository: {e}")

        commits = []

        # Build git log arguments
        log_args = []
        if filters.get("since"):
            log_args.append(f'--since={filters["since"]}')
        if filters.get("until"):
            log_args.append(f'--until={filters["until"]}')
        if filters.get("author"):
            log_args.append(f'--author={filters["author"]}')
        if filters.get("max_commits"):
            log_args.append(f'-{filters["max_commits"]}')

        try:
            for commit in repo.iter_commits(*log_args):
                # Get files changed
                files_changed = list(commit.stats.files.keys())

                # Calculate stats
                stats = commit.stats.total

                commit_info = CommitInfo(
                    hash=commit.hexsha[:7],
                    message=commit.message.strip(),
                    author=str(commit.author),
                    date=datetime.fromtimestamp(commit.committed_date),
                    files_changed=files_changed,
                    additions=stats.get("insertions", 0),
                    deletions=stats.get("deletions", 0),
                )
                commits.append(commit_info)
        except Exception as e:
            self.logger.error(f"Error analyzing commits: {e}")

        return commits

    def extract_code_files(self, repo_path: Path, **filters) -> List[CodeFile]:
        """
        Extract and process code files from repository.

        Args:
            repo_path: Path to repository
            **filters: File filtering criteria:
                - extensions: List of allowed extensions
                - languages: List of allowed languages
                - exclude_patterns: Patterns to exclude
                - max_size: Maximum file size

        Returns:
            list: Processed code files
        """
        code_files = []

        for file_path in repo_path.rglob("*"):
            if not file_path.is_file():
                continue

            # Apply filters
            if filters.get("extensions"):
                if file_path.suffix not in filters["extensions"]:
                    continue

            if filters.get("exclude_patterns"):
                if any(
                    re.match(pattern, str(file_path))
                    for pattern in filters["exclude_patterns"]
                ):
                    continue

            if filters.get("max_size"):
                if file_path.stat().st_size > filters["max_size"]:
                    continue

            # Skip common non-code files
            if file_path.name in [".gitignore", ".gitkeep", ".gitattributes"]:
                continue

            if file_path.suffix in [".pyc", ".pyo", ".pyd", ".so", ".dll"]:
                continue

            try:
                code_file = self.code_extractor.extract_file_content(file_path)

                # Apply language filter
                if filters.get("languages"):
                    if code_file.language not in filters["languages"]:
                        continue

                code_files.append(code_file)
            except Exception as e:
                self.logger.debug(f"Failed to extract {file_path}: {e}")

        return code_files

    def get_repository_info(
        self, repo_url: str, repo: Optional[git.Repo] = None
    ) -> Dict[str, Any]:
        """
        Get repository metadata and information.

        Args:
            repo_url: Repository URL
            repo: Git repository object (optional)

        Returns:
            dict: Repository information
        """
        info = {"url": repo_url, "branches": [], "tags": [], "remote_info": {}}

        if repo:
            try:
                info["branches"] = [branch.name for branch in repo.branches]
                info["tags"] = [tag.name for tag in repo.tags]

                # Get remote information
                if repo.remotes:
                    remote = repo.remotes.origin
                    info["remote_info"] = {"url": remote.url, "name": remote.name}

                # Get latest commit
                if repo.heads:
                    latest_commit = repo.head.commit
                    info["latest_commit"] = {
                        "hash": latest_commit.hexsha[:7],
                        "message": latest_commit.message.strip(),
                        "author": str(latest_commit.author),
                        "date": datetime.fromtimestamp(
                            latest_commit.committed_date
                        ).isoformat(),
                    }
            except Exception as e:
                self.logger.warning(f"Error getting repository info: {e}")

        return info

    def _get_temp_dir(self) -> str:
        """Get or create temporary directory for cloning."""
        if self.temp_dir is None:
            self.temp_dir = tempfile.mkdtemp(prefix="semantica_repo_")
        return self.temp_dir

    def cleanup(self):
        """Cleanup temporary repository files."""
        if self.temp_dir and os.path.exists(self.temp_dir):
            def onexc(func, path, exc_info):
                """
                Error handler for shutil.rmtree.

                If the error is due to an access error (read only file)
                it attempts to add write permission and then retries.

                If the error is for another reason it re-raises the error.

                Usage : shutil.rmtree(path, onerror=onexc)
                """
                import stat
                if not os.access(path, os.W_OK):
                    # Is the error an access error ?
                    os.chmod(path, stat.S_IWUSR)
                    func(path)
                else:
                    raise

            try:
                shutil.rmtree(self.temp_dir, onerror=onexc)
            except Exception as e:
                self.logger.warning(f"Failed to clean up temp dir {self.temp_dir}: {e}")

            self.temp_dir = None
