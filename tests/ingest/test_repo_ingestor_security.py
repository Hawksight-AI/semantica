"""Security-focused tests for RepoIngestor (issue #868)."""

import socket
import threading
from unittest.mock import MagicMock, patch

import pytest

from semantica.ingest import repo_ingestor as repo_ingestor_mod
from semantica.ingest.repo_ingestor import (
    ALLOWED_CLONE_OPTIONS,
    RepoIngestor,
)
from semantica.utils.exceptions import ValidationError


def _fake_addrinfo(*addrs: str):
    """Build a getaddrinfo-shaped result list for the given IP strings."""
    results = []
    for addr in addrs:
        family = socket.AF_INET6 if ":" in addr else socket.AF_INET
        results.append(
            (family, socket.SOCK_STREAM, 0, "", (addr, 0))
        )
    return results


@pytest.fixture(autouse=True)
def _clear_repo_host_resolve_cache():
    repo_ingestor_mod._REPO_HOST_RESOLVE_CACHE.clear()
    yield
    repo_ingestor_mod._REPO_HOST_RESOLVE_CACHE.clear()


class TestRepoUrlValidation:
    def test_accepts_https_github_url(self):
        with patch(
            "semantica.ingest.repo_ingestor.socket.getaddrinfo",
            return_value=_fake_addrinfo("140.82.112.3"),
        ):
            RepoIngestor._validate_repo_url("https://github.com/user/repo.git")

    def test_accepts_ssh_scheme(self):
        with patch(
            "semantica.ingest.repo_ingestor.socket.getaddrinfo",
            return_value=_fake_addrinfo("140.82.112.3"),
        ):
            RepoIngestor._validate_repo_url("ssh://git@github.com/user/repo.git")

    def test_accepts_scp_like_ssh_remote(self):
        with patch(
            "semantica.ingest.repo_ingestor.socket.getaddrinfo",
            return_value=_fake_addrinfo("140.82.112.3"),
        ):
            RepoIngestor._validate_repo_url("git@github.com:user/repo.git")
            RepoIngestor._validate_repo_url(
                "deploy@gitlab.example.com:team/app.git"
            )

    def test_normalizes_scp_like_to_ssh_url(self):
        assert (
            RepoIngestor._normalize_repo_url("git@github.com:user/repo.git")
            == "ssh://git@github.com/user/repo.git"
        )
        assert (
            RepoIngestor._normalize_repo_url(
                "https://github.com/user/repo.git"
            )
            == "https://github.com/user/repo.git"
        )

    def test_rejects_empty(self):
        with pytest.raises(ValidationError, match="non-empty"):
            RepoIngestor._validate_repo_url("")

    def test_rejects_file_scheme(self):
        with pytest.raises(ValidationError, match="Unsupported repository URL scheme"):
            RepoIngestor._validate_repo_url("file:///tmp/repo.git")

    def test_rejects_env_var_tokens(self):
        with pytest.raises(ValidationError, match="environment variable"):
            RepoIngestor._validate_repo_url(
                "https://attacker.example/${AWS_SECRET_ACCESS_KEY}/repo.git"
            )
        with pytest.raises(ValidationError, match="environment variable"):
            RepoIngestor._validate_repo_url(
                "https://$GITHUB_TOKEN@attacker.example/repo.git"
            )
        with pytest.raises(ValidationError, match="environment variable"):
            RepoIngestor._validate_repo_url(
                "git@github.com:org/${AWS_SECRET_ACCESS_KEY}.git"
            )

    def test_accepts_literal_dollar_without_env_var_token(self):
        with patch(
            "semantica.ingest.repo_ingestor.socket.getaddrinfo",
            return_value=_fake_addrinfo("140.82.112.3"),
        ):
            RepoIngestor._validate_repo_url("https://example.com/repo$1.git")
            RepoIngestor._validate_repo_url("git@example.com:team/repo$1.git")

    def test_rejects_localhost_and_loopback(self):
        with pytest.raises(ValidationError, match="not allowed|blocked"):
            RepoIngestor._validate_repo_url("https://localhost/repo.git")
        with pytest.raises(ValidationError, match="blocked"):
            RepoIngestor._validate_repo_url("https://127.0.0.1/repo.git")
        with pytest.raises(ValidationError, match="not allowed|blocked"):
            RepoIngestor._validate_repo_url("git@localhost:repo.git")
        with pytest.raises(ValidationError, match="blocked"):
            RepoIngestor._validate_repo_url("git@127.0.0.1:repo.git")

    def test_rejects_private_and_metadata_ips(self):
        for url in (
            "https://10.0.0.1/repo.git",
            "https://192.168.1.1/repo.git",
            "https://172.16.5.5/repo.git",
            "http://169.254.169.254/latest/meta-data/",
            "git@10.0.0.1:repo.git",
            "git@169.254.169.254:repo.git",
        ):
            with pytest.raises(ValidationError, match="blocked"):
                RepoIngestor._validate_repo_url(url)

    def test_rejects_hostname_resolving_to_private_ip(self):
        with patch(
            "semantica.ingest.repo_ingestor.socket.getaddrinfo",
            return_value=_fake_addrinfo("10.0.0.5"),
        ):
            with pytest.raises(ValidationError, match="blocked"):
                RepoIngestor._validate_repo_url(
                    "https://internal.example/repo.git"
                )

    def test_rejects_hostname_if_any_resolved_ip_is_blocked(self):
        with patch(
            "semantica.ingest.repo_ingestor.socket.getaddrinfo",
            return_value=_fake_addrinfo("8.8.8.8", "127.0.0.1"),
        ):
            with pytest.raises(ValidationError, match="blocked"):
                RepoIngestor._validate_repo_url(
                    "https://mixed.example/repo.git"
                )

    def test_rejects_unresolvable_hostname(self):
        with patch(
            "semantica.ingest.repo_ingestor.socket.getaddrinfo",
            side_effect=socket.gaierror(8, "Name or service not known"),
        ):
            with pytest.raises(ValidationError, match="Cannot resolve"):
                RepoIngestor._validate_repo_url(
                    "https://does-not-resolve.invalid/repo.git"
                )

    def test_hostname_resolution_is_cached(self):
        with patch(
            "semantica.ingest.repo_ingestor.socket.getaddrinfo",
            return_value=_fake_addrinfo("1.2.3.4"),
        ) as mock_gai:
            RepoIngestor._validate_repo_url("https://cached.example/repo.git")
            RepoIngestor._validate_repo_url("https://cached.example/other.git")
            assert mock_gai.call_count == 1

    def test_rejects_malformed_netloc_as_validation_error(self):
        with pytest.raises(ValidationError, match="Invalid repository URL"):
            RepoIngestor._validate_repo_url("http://[::1")
        with pytest.raises(ValidationError, match="Invalid repository URL"):
            RepoIngestor._validate_repo_url("http://[")
        with pytest.raises(ValidationError, match="Invalid repository URL"):
            RepoIngestor._validate_repo_url("https://user@[::1/repo.git")

    def test_malformed_url_surfaces_as_validation_error_from_ingest(self):
        with patch("semantica.ingest.repo_ingestor.git.Repo") as MockRepo, patch(
            "semantica.ingest.repo_ingestor.get_progress_tracker"
        ) as mock_get_tracker:
            mock_get_tracker.return_value = MagicMock()
            ingestor = RepoIngestor()
            with pytest.raises(ValidationError, match="Invalid repository URL"):
                ingestor.ingest_repository("http://[::1")
            MockRepo.clone_from.assert_not_called()


class TestCloneOptionAllowlist:
    def test_allows_safe_options(self):
        filtered = RepoIngestor._filter_clone_options(
            {"depth": 1, "branch": "main", "single_branch": True, "no_tags": True}
        )
        assert filtered == {
            "depth": 1,
            "branch": "main",
            "single_branch": True,
            "no_tags": True,
        }

    def test_strips_processing_options_without_error(self):
        filtered = RepoIngestor._filter_clone_options(
            {
                "depth": 1,
                "include_history": True,
                "include_extensions": ["py"],
                "file_filters": {},
                "commit_filters": {},
                "max_depth": 5,
            }
        )
        assert filtered == {"depth": 1}

    def test_rejects_multi_options(self):
        with pytest.raises(ValidationError, match="not permitted"):
            RepoIngestor._filter_clone_options(
                {"multi_options": ["--template=/tmp/evil"]}
            )

    def test_rejects_upload_pack_and_template(self):
        for key in ("upload_pack", "template", "config", "env"):
            with pytest.raises(ValidationError, match="not permitted"):
                RepoIngestor._filter_clone_options({key: "x"})

    def test_allowlist_matches_documented_safe_set(self):
        assert ALLOWED_CLONE_OPTIONS == {
            "depth",
            "branch",
            "single_branch",
            "no_tags",
        }


class TestIngestRepositoryGuards:
    def test_unsafe_url_never_reaches_clone_from(self):
        with patch("semantica.ingest.repo_ingestor.git.Repo") as MockRepo, patch(
            "semantica.ingest.repo_ingestor.get_progress_tracker"
        ) as mock_get_tracker:
            mock_get_tracker.return_value = MagicMock()
            ingestor = RepoIngestor()
            with pytest.raises(ValidationError, match="environment variable"):
                ingestor.ingest_repository(
                    "https://evil.example/${AWS_SECRET_ACCESS_KEY}/r.git"
                )
            MockRepo.clone_from.assert_not_called()

    def test_unsafe_clone_option_never_reaches_clone_from(self):
        with patch("semantica.ingest.repo_ingestor.git.Repo") as MockRepo, patch(
            "semantica.ingest.repo_ingestor.get_progress_tracker"
        ) as mock_get_tracker, patch(
            "semantica.ingest.repo_ingestor.socket.getaddrinfo",
            return_value=_fake_addrinfo("140.82.112.3"),
        ):
            mock_get_tracker.return_value = MagicMock()
            ingestor = RepoIngestor()
            with pytest.raises(ValidationError, match="not permitted"):
                ingestor.ingest_repository(
                    "https://github.com/user/repo.git",
                    multi_options=["--template=/tmp/evil"],
                )
            MockRepo.clone_from.assert_not_called()

    def test_hostname_resolving_private_never_reaches_clone_from(self):
        with patch("semantica.ingest.repo_ingestor.git.Repo") as MockRepo, patch(
            "semantica.ingest.repo_ingestor.get_progress_tracker"
        ) as mock_get_tracker, patch(
            "semantica.ingest.repo_ingestor.socket.getaddrinfo",
            return_value=_fake_addrinfo("192.168.1.50"),
        ):
            mock_get_tracker.return_value = MagicMock()
            ingestor = RepoIngestor()
            with pytest.raises(ValidationError, match="blocked"):
                ingestor.ingest_repository(
                    "https://ssrf.example/internal/repo.git"
                )
            MockRepo.clone_from.assert_not_called()

    def test_safe_options_forwarded_to_clone_from(self):
        with patch("semantica.ingest.repo_ingestor.git.Repo") as MockRepo, patch(
            "semantica.ingest.repo_ingestor.tempfile.mkdtemp",
            return_value="/tmp/fake-repo",
        ), patch("semantica.ingest.repo_ingestor.shutil.rmtree"), patch(
            "semantica.ingest.repo_ingestor.get_progress_tracker"
        ) as mock_get_tracker, patch(
            "semantica.ingest.repo_ingestor.socket.getaddrinfo",
            return_value=_fake_addrinfo("140.82.112.3"),
        ), patch.object(
            RepoIngestor, "extract_code_files", return_value=[]
        ), patch.object(
            RepoIngestor, "get_repository_info", return_value={"url": "x"}
        ), patch.object(RepoIngestor, "analyze_commits", return_value=[]):
            mock_get_tracker.return_value = MagicMock()
            mock_repo = MagicMock()
            MockRepo.clone_from.return_value = mock_repo
            MockRepo.return_value = mock_repo

            ingestor = RepoIngestor()
            with patch.object(
                ingestor.analyzer, "analyze_structure", return_value={}
            ), patch.object(
                ingestor.analyzer, "calculate_metrics", return_value={}
            ):
                ingestor.ingest_repository(
                    "https://github.com/user/repo.git",
                    depth=1,
                    branch="main",
                    include_history=False,
                )

            kwargs = MockRepo.clone_from.call_args.kwargs
            assert kwargs.get("depth") == 1
            assert kwargs.get("branch") == "main"
            assert "include_history" not in kwargs
            assert "multi_options" not in kwargs

    def test_scp_like_remote_normalized_before_clone(self):
        with patch("semantica.ingest.repo_ingestor.git.Repo") as MockRepo, patch(
            "semantica.ingest.repo_ingestor.tempfile.mkdtemp",
            return_value="/tmp/fake-repo",
        ), patch("semantica.ingest.repo_ingestor.shutil.rmtree"), patch(
            "semantica.ingest.repo_ingestor.get_progress_tracker"
        ) as mock_get_tracker, patch(
            "semantica.ingest.repo_ingestor.socket.getaddrinfo",
            return_value=_fake_addrinfo("140.82.112.3"),
        ), patch.object(
            RepoIngestor, "extract_code_files", return_value=[]
        ), patch.object(
            RepoIngestor, "get_repository_info", return_value={"url": "x"}
        ), patch.object(RepoIngestor, "analyze_commits", return_value=[]):
            mock_get_tracker.return_value = MagicMock()
            mock_repo = MagicMock()
            MockRepo.clone_from.return_value = mock_repo
            MockRepo.return_value = mock_repo

            ingestor = RepoIngestor()
            with patch.object(
                ingestor.analyzer, "analyze_structure", return_value={}
            ), patch.object(
                ingestor.analyzer, "calculate_metrics", return_value={}
            ):
                ingestor.ingest_repository("git@github.com:user/repo.git")

            assert MockRepo.clone_from.call_args.args[0] == (
                "ssh://git@github.com/user/repo.git"
            )

class TestIsReservedNAT64Regression:
    """Regression tests for the is_reserved / NAT64 false-positive fix.

    Python's ipaddress.is_reserved marks 64:ff9b::/96 (NAT64 Well-Known
    Prefix, RFC 6052) as reserved=True, which caused github.com to be
    falsely blocked on IPv6-only / dual-stack networks that use NAT64.
    """

    def test_nat64_prefix_not_blocked(self):
        """64:ff9b::/96 addresses must not be blocked by _is_blocked_ip."""
        import ipaddress

        # Typical NAT64 translation of 140.82.112.3 (github.com)
        addr = ipaddress.ip_address("64:ff9b::8c52:7003")
        assert not RepoIngestor._is_blocked_ip(addr), (
            "NAT64 WKP address should not be blocked; "
            "it is a legitimate public IPv6 address on NAT64 networks."
        )

    def test_nat64_local_prefix_not_blocked(self):
        """64:ff9b:1::/48 (RFC 8215 local NAT64) is private by Python 3.12
        definition and IS correctly blocked — it's a locally-assigned range,
        not globally routable.
        """
        import ipaddress

        addr = ipaddress.ip_address("64:ff9b:1::1")
        # is_private=True in Python 3.12 — legitimately blocked
        assert RepoIngestor._is_blocked_ip(addr)

    def test_private_ipv6_still_blocked(self):
        """ULA (fc00::/7) must still be blocked."""
        import ipaddress

        assert RepoIngestor._is_blocked_ip(ipaddress.ip_address("fc00::1"))
        assert RepoIngestor._is_blocked_ip(ipaddress.ip_address("fd12:3456::1"))

    def test_ipv6_loopback_still_blocked(self):
        import ipaddress

        assert RepoIngestor._is_blocked_ip(ipaddress.ip_address("::1"))

    def test_ipv6_link_local_still_blocked(self):
        import ipaddress

        assert RepoIngestor._is_blocked_ip(ipaddress.ip_address("fe80::1"))

    def test_documentation_prefix_blocked(self):
        """2001:db8::/32 is documentation-only and classified as
        is_private=True in Python 3.12. It is correctly blocked.
        """
        import ipaddress

        addr = ipaddress.ip_address("2001:db8::1")
        assert RepoIngestor._is_blocked_ip(addr)

    def test_public_ipv4_not_blocked(self):
        import ipaddress

        assert not RepoIngestor._is_blocked_ip(ipaddress.ip_address("140.82.112.3"))

    def test_public_ipv6_not_blocked(self):
        import ipaddress

        assert not RepoIngestor._is_blocked_ip(
            ipaddress.ip_address("2001:4860:4860::8888")
        )

    def test_host_resolving_to_nat64_address_is_allowed(self):
        """A hostname that resolves to a NAT64 address (plus a public IPv4)
        must not be blocked — this was the real-world failure mode.
        """
        # Simulate github.com on a NAT64 network
        with patch(
            "semantica.ingest.repo_ingestor.socket.getaddrinfo",
            return_value=_fake_addrinfo("64:ff9b::8c52:7003", "140.82.112.3"),
        ):
            # Should not raise
            RepoIngestor._validate_repo_url("https://github.com/user/repo.git")

    def test_host_resolving_only_to_nat64_is_allowed(self):
        """Even if the only resolved address is a NAT64 address, it is allowed
        because it is a valid public address.
        """
        with patch(
            "semantica.ingest.repo_ingestor.socket.getaddrinfo",
            return_value=_fake_addrinfo("64:ff9b::8c52:7003"),
        ):
            RepoIngestor._validate_repo_url("https://github.com/user/repo.git")


class TestLocalPathSupport:
    """Regression tests for local repository path backward compatibility."""

    def test_is_local_repo_path_absolute(self, tmp_path):
        """Absolute paths are recognised as local."""
        assert RepoIngestor._is_local_repo_path(str(tmp_path))

    def test_is_local_repo_path_relative(self):
        """./… and ../… are recognised as local."""
        assert RepoIngestor._is_local_repo_path("./repo")
        assert RepoIngestor._is_local_repo_path("../sibling-repo")

    def test_is_local_repo_path_not_remote(self):
        """Remote URLs are not local."""
        assert not RepoIngestor._is_local_repo_path("https://github.com/u/r.git")
        assert not RepoIngestor._is_local_repo_path("git@github.com:u/r.git")
        assert not RepoIngestor._is_local_repo_path("ssh://git@github.com/r.git")

    def test_validate_repo_url_accepts_absolute_local_path(self, tmp_path):
        """_validate_repo_url must not raise for an absolute local path."""
        RepoIngestor._validate_repo_url(str(tmp_path))

    def test_validate_repo_url_accepts_relative_local_path(self):
        """_validate_repo_url must not raise for ./… paths."""
        RepoIngestor._validate_repo_url("./repo")

    def test_validate_repo_url_env_var_still_blocked_in_local_path(self):
        """Env-var tokens in local paths are still rejected."""
        with pytest.raises(ValidationError, match="environment variable"):
            RepoIngestor._validate_repo_url("./$SECRET_KEY/repo")

    def test_local_path_never_reaches_dns_resolution(self, tmp_path):
        """Local paths must not trigger DNS lookups."""
        with patch(
            "semantica.ingest.repo_ingestor.socket.getaddrinfo"
        ) as mock_gai:
            RepoIngestor._validate_repo_url(str(tmp_path))
        mock_gai.assert_not_called()

    def test_ingest_repository_local_path_passes_validation(self, tmp_path):
        """ingest_repository with a local path must not fail at URL validation."""
        with patch("semantica.ingest.repo_ingestor.git.Repo") as MockRepo, patch(
            "semantica.ingest.repo_ingestor.get_progress_tracker"
        ) as mock_get_tracker:
            mock_get_tracker.return_value = MagicMock()
            ingestor = RepoIngestor()
            # Expect clone to fail (temp_dir logic), but NOT a ValidationError
            try:
                ingestor.ingest_repository(str(tmp_path))
            except Exception as exc:
                assert not isinstance(exc, ValidationError), (
                    f"Local path must not raise ValidationError; got: {exc}"
                )


class TestRepoHostResolveCacheThreadSafety:
    """Regression test: _REPO_HOST_RESOLVE_CACHE must survive concurrent use.

    _REPO_HOST_RESOLVE_CACHE is a module-level OrderedDict shared across every
    RepoIngestor instance and thread. Before the fix, _resolve_repo_host_ips
    and _prune_repo_host_resolve_cache read, wrote, and iterated the dict with
    no lock. Under concurrent host validation (e.g. multiple
    ingest_repository() calls running in a thread pool), one thread's
    insert/evict during another thread's iteration reliably raised
    RuntimeError: OrderedDict mutated during iteration.
    """

    def test_concurrent_resolve_repo_host_ips_does_not_raise(self):
        def fake_getaddrinfo(host, *args, **kwargs):
            return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("93.184.216.34", 0))]

        orig_ttl = repo_ingestor_mod._REPO_HOST_RESOLVE_CACHE_TTL_SECONDS
        orig_max = repo_ingestor_mod._REPO_HOST_RESOLVE_CACHE_MAX_ENTRIES
        # Small TTL/cap so eviction and pruning happen on nearly every call,
        # keeping the dict under constant mutation without needing an
        # unreasonably large iteration count.
        repo_ingestor_mod._REPO_HOST_RESOLVE_CACHE_TTL_SECONDS = 0.001
        repo_ingestor_mod._REPO_HOST_RESOLVE_CACHE_MAX_ENTRIES = 8

        errors = []
        errors_lock = threading.Lock()

        def worker(worker_id):
            for i in range(500):
                host = f"race-host-{worker_id}-{i}.example.com"
                try:
                    repo_ingestor_mod.RepoIngestor._resolve_repo_host_ips(host)
                except Exception as exc:  # pragma: no cover - failure path
                    with errors_lock:
                        errors.append(exc)

        try:
            with patch(
                "semantica.ingest.repo_ingestor.socket.getaddrinfo",
                side_effect=fake_getaddrinfo,
            ):
                # daemon=True so a hung worker cannot also block the test
                # process from exiting once it's reported below.
                threads = [
                    threading.Thread(target=worker, args=(n,), daemon=True)
                    for n in range(32)
                ]
                for t in threads:
                    t.start()
                # Assert right after each join, not after the whole loop:
                # join(timeout=30) alone does not fail the test if a thread
                # hangs, and checking only once every thread has been
                # joined means a mass hang costs up to 32*30s = 16 minutes
                # before the test even reaches the check -- the exact
                # CI-reliability problem this guards against. Failing on
                # the first hung thread caps the worst case at ~30s.
                for t in threads:
                    t.join(timeout=30)
                    assert not t.is_alive(), (
                        f"worker thread {t.name} did not finish within "
                        f"the 30s join timeout (still running)"
                    )
        finally:
            repo_ingestor_mod._REPO_HOST_RESOLVE_CACHE_TTL_SECONDS = orig_ttl
            repo_ingestor_mod._REPO_HOST_RESOLVE_CACHE_MAX_ENTRIES = orig_max

        assert not errors, (
            f"Concurrent host resolution raised {len(errors)} error(s); "
            f"first: {errors[0]!r}"
        )
