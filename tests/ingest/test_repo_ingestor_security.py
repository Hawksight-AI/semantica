"""Security-focused tests for RepoIngestor (issue #868)."""

import socket
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
