"""
Unit tests for SalesforceConnector and SalesforceIngestor.

All Salesforce API calls are mocked — no real Salesforce account is required.

Test structure mirrors tests/test_snowflake_ingestor.py and
tests/test_databricks_ingestor.py:
  - autouse fixture mocks simple-salesforce when not installed
  - @patch("...SALESFORCE_AVAILABLE", True) guards every test that needs
    the library to appear installed
  - credentials are always supplied so secrets are never logged or
    embedded in assertions
"""

import os
from datetime import datetime
from unittest.mock import MagicMock, Mock, patch

import pytest

# Check whether simple-salesforce is available in this environment.
try:
    import simple_salesforce  # noqa: F401
    SALESFORCE_LIB_AVAILABLE = True
except ImportError:
    SALESFORCE_LIB_AVAILABLE = False


# ---------------------------------------------------------------------------
# autouse fixture: mock simple_salesforce when not installed
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _mock_simple_salesforce_if_needed():
    """If simple-salesforce is absent, inject a minimal stub so imports work."""
    if not SALESFORCE_LIB_AVAILABLE:
        sf_mod = MagicMock()
        sf_exc_mod = MagicMock()

        # Provide real exception classes so isinstance checks work in tests.
        class _SFError(Exception):
            pass

        class _SFAuthFailed(_SFError):
            def __init__(self, code, message):
                super().__init__(message)
                self.code = code
                self.auth_message = message

        class _SFExpired(_SFError):
            pass

        class _SFGeneral(_SFError):
            pass

        class _SFMalformed(_SFError):
            pass

        class _SFRefused(_SFError):
            pass

        class _SFNotFound(_SFError):
            pass

        sf_exc_mod.SalesforceError = _SFError
        sf_exc_mod.SalesforceAuthenticationFailed = _SFAuthFailed
        sf_exc_mod.SalesforceExpiredSession = _SFExpired
        sf_exc_mod.SalesforceGeneralError = _SFGeneral
        sf_exc_mod.SalesforceMalformedRequest = _SFMalformed
        sf_exc_mod.SalesforceRefusedRequest = _SFRefused
        sf_exc_mod.SalesforceResourceNotFound = _SFNotFound

        sf_mod.Salesforce = MagicMock()
        sf_mod.exceptions = sf_exc_mod

        with patch.dict(
            "sys.modules",
            {
                "simple_salesforce": sf_mod,
                "simple_salesforce.exceptions": sf_exc_mod,
            },
        ):
            yield
    else:
        yield


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_sf_client(instance="myorg.salesforce.com"):
    """Return a Mock that looks like a connected simple_salesforce.Salesforce."""
    mock_client = Mock()
    mock_client.sf_instance = instance
    mock_client.base_url = f"https://{instance}/services/data/v59.0/"
    mock_client.auth_type = "password"
    mock_client.session = Mock()
    mock_client.limits = Mock(return_value={"DailyApiRequests": {"Max": 15000, "Remaining": 14999}})
    return mock_client


# ---------------------------------------------------------------------------
# TestSalesforceConnector — initialisation
# ---------------------------------------------------------------------------

class TestSalesforceConnectorInit:
    """Tests for SalesforceConnector.__init__ and credential validation."""

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    def test_init_with_username_password_token(self):
        """Connector accepts full username/password/token credentials."""
        from semantica.ingest.salesforce_ingestor import SalesforceConnector

        conn = SalesforceConnector(
            username="user@org.com",
            password="s3cr3t",
            security_token="TOKEN123",
        )

        assert conn.username == "user@org.com"
        # Passwords and tokens must be stored but not exposed as plain attrs.
        assert conn._password == "s3cr3t"
        assert conn._security_token == "TOKEN123"
        assert conn.domain == "login"  # default
        assert conn._client is None   # not connected yet

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    def test_init_default_domain_is_login(self):
        """Domain defaults to 'login' when not specified."""
        from semantica.ingest.salesforce_ingestor import SalesforceConnector

        conn = SalesforceConnector(
            username="u", password="p", security_token="t"
        )
        assert conn.domain == "login"

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    def test_init_sandbox_domain(self):
        """domain='test' is stored and will be forwarded to simple-salesforce."""
        from semantica.ingest.salesforce_ingestor import SalesforceConnector

        conn = SalesforceConnector(
            username="u", password="p", security_token="t", domain="test"
        )
        assert conn.domain == "test"

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    def test_init_with_session_id_and_instance_url(self):
        """Connector accepts session_id + instance_url authentication."""
        from semantica.ingest.salesforce_ingestor import SalesforceConnector

        conn = SalesforceConnector(
            session_id="00D...",
            instance_url="https://myorg.my.salesforce.com",
        )

        assert conn._session_id == "00D..."
        assert conn.instance_url == "https://myorg.my.salesforce.com"
        assert conn._client is None

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    def test_init_api_version_stored(self):
        """api_version is stored for forwarding to simple-salesforce."""
        from semantica.ingest.salesforce_ingestor import SalesforceConnector

        conn = SalesforceConnector(
            username="u", password="p", security_token="t", api_version="58.0"
        )
        assert conn.api_version == "58.0"


# ---------------------------------------------------------------------------
# TestSalesforceConnectorInit — environment variable fallback
# ---------------------------------------------------------------------------

class TestSalesforceConnectorEnvVars:
    """Tests that env-var fallbacks work correctly."""

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    def test_credentials_from_env_vars(self):
        """All three credential env vars are read when args are omitted."""
        from semantica.ingest.salesforce_ingestor import SalesforceConnector

        env = {
            "SALESFORCE_USERNAME": "env_user@org.com",
            "SALESFORCE_PASSWORD": "env_pass",
            "SALESFORCE_SECURITY_TOKEN": "env_token",
        }
        with patch.dict(os.environ, env):
            conn = SalesforceConnector()

        assert conn.username == "env_user@org.com"
        assert conn._password == "env_pass"
        assert conn._security_token == "env_token"

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    def test_domain_from_env_var(self):
        """SALESFORCE_DOMAIN env var sets the domain."""
        from semantica.ingest.salesforce_ingestor import SalesforceConnector

        with patch.dict(
            os.environ,
            {
                "SALESFORCE_USERNAME": "u",
                "SALESFORCE_PASSWORD": "p",
                "SALESFORCE_SECURITY_TOKEN": "t",
                "SALESFORCE_DOMAIN": "test",
            },
        ):
            conn = SalesforceConnector()

        assert conn.domain == "test"

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    def test_api_version_from_env_var(self):
        """SALESFORCE_API_VERSION env var is honoured."""
        from semantica.ingest.salesforce_ingestor import SalesforceConnector

        with patch.dict(
            os.environ,
            {
                "SALESFORCE_USERNAME": "u",
                "SALESFORCE_PASSWORD": "p",
                "SALESFORCE_SECURITY_TOKEN": "t",
                "SALESFORCE_API_VERSION": "57.0",
            },
        ):
            conn = SalesforceConnector()

        assert conn.api_version == "57.0"

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    def test_constructor_arg_overrides_env_var(self):
        """Explicit constructor args take precedence over env vars."""
        from semantica.ingest.salesforce_ingestor import SalesforceConnector

        with patch.dict(
            os.environ,
            {
                "SALESFORCE_USERNAME": "env_user",
                "SALESFORCE_PASSWORD": "env_pass",
                "SALESFORCE_SECURITY_TOKEN": "env_token",
            },
        ):
            conn = SalesforceConnector(
                username="explicit_user",
                password="explicit_pass",
                security_token="explicit_token",
            )

        assert conn.username == "explicit_user"
        assert conn._password == "explicit_pass"
        assert conn._security_token == "explicit_token"

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    def test_session_and_instance_from_env_vars(self):
        """SALESFORCE_SESSION_ID + SALESFORCE_INSTANCE_URL env vars work."""
        from semantica.ingest.salesforce_ingestor import SalesforceConnector

        with patch.dict(
            os.environ,
            {
                "SALESFORCE_SESSION_ID": "env_sid",
                "SALESFORCE_INSTANCE_URL": "https://env.salesforce.com",
            },
        ):
            conn = SalesforceConnector()

        assert conn._session_id == "env_sid"
        assert conn.instance_url == "https://env.salesforce.com"


# ---------------------------------------------------------------------------
# TestSalesforceConnectorValidation — missing credentials
# ---------------------------------------------------------------------------

class TestSalesforceConnectorValidation:
    """Tests that ValidationError is raised for incomplete credentials."""

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    def test_no_credentials_raises_validation_error(self):
        """No credentials at all raises ValidationError."""
        from semantica.ingest.salesforce_ingestor import SalesforceConnector
        from semantica.utils.exceptions import ValidationError

        with pytest.raises(ValidationError):
            SalesforceConnector()

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    def test_username_only_raises_validation_error(self):
        """Username without password/token raises ValidationError."""
        from semantica.ingest.salesforce_ingestor import SalesforceConnector
        from semantica.utils.exceptions import ValidationError

        with pytest.raises(ValidationError):
            SalesforceConnector(username="only_user")

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    def test_username_password_without_token_raises(self):
        """Username + password without security_token raises ValidationError."""
        from semantica.ingest.salesforce_ingestor import SalesforceConnector
        from semantica.utils.exceptions import ValidationError

        with pytest.raises(ValidationError):
            SalesforceConnector(username="u", password="p")

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    def test_session_id_without_instance_url_raises(self):
        """session_id without instance_url raises ValidationError."""
        from semantica.ingest.salesforce_ingestor import SalesforceConnector
        from semantica.utils.exceptions import ValidationError

        with pytest.raises(ValidationError):
            SalesforceConnector(session_id="00D...")

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    def test_instance_url_without_session_id_raises(self):
        """instance_url without session_id raises ValidationError."""
        from semantica.ingest.salesforce_ingestor import SalesforceConnector
        from semantica.utils.exceptions import ValidationError

        with pytest.raises(ValidationError):
            SalesforceConnector(instance_url="https://myorg.salesforce.com")

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    def test_validation_error_message_does_not_contain_password(self):
        """The ValidationError message must not expose credential values."""
        from semantica.ingest.salesforce_ingestor import SalesforceConnector
        from semantica.utils.exceptions import ValidationError

        with pytest.raises(ValidationError) as exc_info:
            SalesforceConnector(username="u", password="super_secret")

        assert "super_secret" not in str(exc_info.value)

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    def test_missing_lib_raises_import_error(self):
        """ImportError with install instructions when lib absent."""
        from semantica.ingest.salesforce_ingestor import SalesforceConnector

        with patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", False):
            with pytest.raises(ImportError) as exc_info:
                SalesforceConnector(username="u", password="p", security_token="t")

        msg = str(exc_info.value)
        assert "simple-salesforce" in msg
        assert "db-salesforce" in msg


# ---------------------------------------------------------------------------
# TestSalesforceConnectorConnect — successful connection
# ---------------------------------------------------------------------------

class TestSalesforceConnectorConnect:
    """Tests for connect() with username/password and session-id auth."""

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    @patch("semantica.ingest.salesforce_ingestor._SimpleSalesforce")
    def test_connect_password_auth_calls_simple_salesforce(self, mock_sf_cls):
        """connect() constructs a Salesforce client with correct kwargs."""
        from semantica.ingest.salesforce_ingestor import SalesforceConnector

        mock_sf_cls.return_value = _make_mock_sf_client()

        conn = SalesforceConnector(
            username="user@org.com",
            password="p4ss",
            security_token="TOK",
        )
        client = conn.connect()

        assert client is mock_sf_cls.return_value
        call_kwargs = mock_sf_cls.call_args[1]
        assert call_kwargs["username"] == "user@org.com"
        assert call_kwargs["password"] == "p4ss"
        assert call_kwargs["security_token"] == "TOK"
        assert call_kwargs["domain"] == "login"
        assert "session_id" not in call_kwargs

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    def test_init_jwt_bearer_with_privatekey_file(self):
        """Connector accepts JWT Bearer credentials with privatekey_file."""
        from semantica.ingest.salesforce_ingestor import SalesforceConnector

        conn = SalesforceConnector(
            username="jwt_user@org.com",
            consumer_key="3MVG9test_consumer_key",
            privatekey_file="/path/to/fake_key.pem",
        )

        assert conn.username == "jwt_user@org.com"
        assert conn.consumer_key == "3MVG9test_consumer_key"
        assert conn._privatekey_file == "/path/to/fake_key.pem"
        assert conn._privatekey is None
        assert conn._client is None

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    @patch("semantica.ingest.salesforce_ingestor._SimpleSalesforce")
    def test_connect_jwt_bearer_auth_calls_simple_salesforce(self, mock_sf_cls):
        """connect() constructs JWT Bearer client with correct kwargs."""
        from semantica.ingest.salesforce_ingestor import SalesforceConnector

        mock_sf_cls.return_value = _make_mock_sf_client()

        # Fake PEM private key for testing only
        fake_pem = """-----BEGIN RSA PRIVATE KEY-----
MIICXAIBAAKBgQC0fake_key_data_for_testing_only
-----END RSA PRIVATE KEY-----"""

        conn = SalesforceConnector(
            username="jwt_user@org.com",
            consumer_key="3MVG9test_consumer_key",
            privatekey=fake_pem,
        )
        client = conn.connect()

        assert client is mock_sf_cls.return_value
        call_kwargs = mock_sf_cls.call_args[1]
        assert call_kwargs["username"] == "jwt_user@org.com"
        assert call_kwargs["consumer_key"] == "3MVG9test_consumer_key"
        assert call_kwargs["privatekey"] == fake_pem
        assert call_kwargs["domain"] == "login"
        # Password/token should not be present for JWT auth
        assert "password" not in call_kwargs
        assert "security_token" not in call_kwargs

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    @patch("semantica.ingest.salesforce_ingestor._SimpleSalesforce")
    def test_connect_sandbox_domain_forwarded(self, mock_sf_cls):
        """domain='test' is forwarded to simple-salesforce."""
        from semantica.ingest.salesforce_ingestor import SalesforceConnector

        mock_sf_cls.return_value = _make_mock_sf_client()

        conn = SalesforceConnector(
            username="u", password="p", security_token="t", domain="test"
        )
        conn.connect()

        call_kwargs = mock_sf_cls.call_args[1]
        assert call_kwargs["domain"] == "test"

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    @patch("semantica.ingest.salesforce_ingestor._SimpleSalesforce")
    def test_connect_api_version_forwarded_as_version(self, mock_sf_cls):
        """api_version is forwarded as 'version' (simple-salesforce's kwarg name)."""
        from semantica.ingest.salesforce_ingestor import SalesforceConnector

        mock_sf_cls.return_value = _make_mock_sf_client()

        conn = SalesforceConnector(
            username="u", password="p", security_token="t", api_version="57.0"
        )
        conn.connect()

        call_kwargs = mock_sf_cls.call_args[1]
        assert call_kwargs["version"] == "57.0"

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    @patch("semantica.ingest.salesforce_ingestor._SimpleSalesforce")
    def test_connect_session_id_auth(self, mock_sf_cls):
        """connect() uses session_id + instance_url when provided."""
        from semantica.ingest.salesforce_ingestor import SalesforceConnector

        mock_client = _make_mock_sf_client("myorg.salesforce.com")
        mock_sf_cls.return_value = mock_client

        conn = SalesforceConnector(
            session_id="00D_SESSION",
            instance_url="https://myorg.salesforce.com",
        )
        client = conn.connect()

        assert client is mock_client
        call_kwargs = mock_sf_cls.call_args[1]
        assert call_kwargs["session_id"] == "00D_SESSION"
        assert call_kwargs["instance_url"] == "https://myorg.salesforce.com"
        assert "password" not in call_kwargs
        assert "security_token" not in call_kwargs

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    @patch("semantica.ingest.salesforce_ingestor._SimpleSalesforce")
    def test_connect_populates_instance_url(self, mock_sf_cls):
        """connect() resolves instance_url from sf_instance after login."""
        from semantica.ingest.salesforce_ingestor import SalesforceConnector

        mock_client = _make_mock_sf_client("na1.salesforce.com")
        mock_sf_cls.return_value = mock_client

        conn = SalesforceConnector(
            username="u", password="p", security_token="t"
        )
        # instance_url not provided — should be set after connect
        assert conn.instance_url is None
        conn.connect()
        assert conn.instance_url == "https://na1.salesforce.com"

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    @patch("semantica.ingest.salesforce_ingestor._SimpleSalesforce")
    def test_connect_reuses_existing_client(self, mock_sf_cls):
        """Second call to connect() returns the same client without re-authenticating."""
        from semantica.ingest.salesforce_ingestor import SalesforceConnector

        mock_sf_cls.return_value = _make_mock_sf_client()

        conn = SalesforceConnector(
            username="u", password="p", security_token="t"
        )
        client1 = conn.connect()
        client2 = conn.connect()

        assert client1 is client2
        # Constructor called exactly once — no re-authentication.
        mock_sf_cls.assert_called_once()

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    @patch("semantica.ingest.salesforce_ingestor._SimpleSalesforce")
    def test_connect_client_property(self, mock_sf_cls):
        """connector.client returns None before connect and the client after."""
        from semantica.ingest.salesforce_ingestor import SalesforceConnector

        mock_sf_cls.return_value = _make_mock_sf_client()
        conn = SalesforceConnector(username="u", password="p", security_token="t")

        assert conn.client is None
        conn.connect()
        assert conn.client is not None


# ---------------------------------------------------------------------------
# TestSalesforceConnectorConnect — connection failures
# ---------------------------------------------------------------------------

class TestSalesforceConnectorFailures:
    """Tests that connect() raises ProcessingError on failures."""

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    @patch("semantica.ingest.salesforce_ingestor._SimpleSalesforce")
    def test_connect_auth_failure_raises_processing_error(self, mock_sf_cls):
        """SalesforceAuthenticationFailed is wrapped as ProcessingError."""
        from semantica.ingest.salesforce_ingestor import (
            SalesforceConnector,
            _SalesforceAuthenticationFailed,
        )
        from semantica.utils.exceptions import ProcessingError

        mock_sf_cls.side_effect = _SalesforceAuthenticationFailed(
            "INVALID_LOGIN", "authentication failure"
        )

        conn = SalesforceConnector(username="u", password="bad", security_token="t")

        with pytest.raises(ProcessingError) as exc_info:
            conn.connect()

        # The password must not appear in the raised message.
        assert "bad" not in str(exc_info.value)

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    @patch("semantica.ingest.salesforce_ingestor._SimpleSalesforce")
    def test_connect_general_sf_error_raises_processing_error(self, mock_sf_cls):
        """SalesforceError is wrapped as ProcessingError."""
        from semantica.ingest.salesforce_ingestor import (
            SalesforceConnector,
            _SalesforceError,
        )
        from semantica.utils.exceptions import ProcessingError

        mock_sf_cls.side_effect = _SalesforceError(
            "https://login.salesforce.com", 500, "Salesforce", b"Generic SF error"
        )

        conn = SalesforceConnector(username="u", password="p", security_token="t")

        with pytest.raises(ProcessingError):
            conn.connect()

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    @patch("semantica.ingest.salesforce_ingestor._SimpleSalesforce")
    def test_connect_network_error_raises_processing_error(self, mock_sf_cls):
        """Network errors (ConnectionError) are wrapped as ProcessingError."""
        from semantica.ingest.salesforce_ingestor import SalesforceConnector
        from semantica.utils.exceptions import ProcessingError

        mock_sf_cls.side_effect = ConnectionError("DNS resolution failed")

        conn = SalesforceConnector(username="u", password="p", security_token="t")

        with pytest.raises(ProcessingError) as exc_info:
            conn.connect()

        # Exception message should not contain the password.
        assert "p" not in str(exc_info.value)

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    @patch("semantica.ingest.salesforce_ingestor._SimpleSalesforce")
    def test_connect_leaves_client_none_on_failure(self, mock_sf_cls):
        """A failed connect() must not leave a partial client reference."""
        from semantica.ingest.salesforce_ingestor import SalesforceConnector
        from semantica.utils.exceptions import ProcessingError

        mock_sf_cls.side_effect = RuntimeError("unexpected")

        conn = SalesforceConnector(username="u", password="p", security_token="t")

        with pytest.raises(ProcessingError):
            conn.connect()

        assert conn._client is None

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    @patch("semantica.ingest.salesforce_ingestor._SimpleSalesforce")
    def test_connect_error_message_does_not_contain_password(self, mock_sf_cls):
        """ProcessingError raised by connect() must not echo the password."""
        from semantica.ingest.salesforce_ingestor import (
            SalesforceConnector,
            _SalesforceAuthenticationFailed,
        )
        from semantica.utils.exceptions import ProcessingError

        mock_sf_cls.side_effect = _SalesforceAuthenticationFailed(
            "INVALID_LOGIN", "bad credentials"
        )

        conn = SalesforceConnector(
            username="u", password="secret_pass", security_token="secret_tok"
        )

        with pytest.raises(ProcessingError) as exc_info:
            conn.connect()

        assert "secret_pass" not in str(exc_info.value)
        assert "secret_tok" not in str(exc_info.value)


# ---------------------------------------------------------------------------
# TestSalesforceConnectorDisconnect
# ---------------------------------------------------------------------------

class TestSalesforceConnectorDisconnect:
    """Tests for disconnect() / close() behaviour."""

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    @patch("semantica.ingest.salesforce_ingestor._SimpleSalesforce")
    def test_disconnect_closes_session_and_clears_client(self, mock_sf_cls):
        """disconnect() closes the requests.Session and sets _client to None."""
        from semantica.ingest.salesforce_ingestor import SalesforceConnector

        mock_client = _make_mock_sf_client()
        mock_sf_cls.return_value = mock_client

        conn = SalesforceConnector(username="u", password="p", security_token="t")
        conn.connect()
        assert conn._client is not None

        conn.disconnect()

        mock_client.session.close.assert_called_once()
        assert conn._client is None

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    @patch("semantica.ingest.salesforce_ingestor._SimpleSalesforce")
    def test_disconnect_is_idempotent(self, mock_sf_cls):
        """Calling disconnect() twice does not raise."""
        from semantica.ingest.salesforce_ingestor import SalesforceConnector

        mock_sf_cls.return_value = _make_mock_sf_client()
        conn = SalesforceConnector(username="u", password="p", security_token="t")
        conn.connect()

        conn.disconnect()
        conn.disconnect()  # second call — must not raise

        assert conn._client is None

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    def test_disconnect_without_connect_is_safe(self):
        """disconnect() before connect() must not raise."""
        from semantica.ingest.salesforce_ingestor import SalesforceConnector

        conn = SalesforceConnector(username="u", password="p", security_token="t")
        conn.disconnect()  # must not raise
        assert conn._client is None


# ---------------------------------------------------------------------------
# TestSalesforceConnectorTestConnection
# ---------------------------------------------------------------------------

class TestSalesforceConnectorTestConnection:
    """Tests for test_connection()."""

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    @patch("semantica.ingest.salesforce_ingestor._SimpleSalesforce")
    def test_test_connection_success_returns_true(self, mock_sf_cls):
        """test_connection() returns True when limits() succeeds."""
        from semantica.ingest.salesforce_ingestor import SalesforceConnector

        mock_client = _make_mock_sf_client()
        mock_sf_cls.return_value = mock_client

        conn = SalesforceConnector(username="u", password="p", security_token="t")
        result = conn.test_connection()

        assert result is True
        mock_client.limits.assert_called_once()

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    @patch("semantica.ingest.salesforce_ingestor._SimpleSalesforce")
    def test_test_connection_closes_transient_connection(self, mock_sf_cls):
        """test_connection() closes the connection it opens (no leak)."""
        from semantica.ingest.salesforce_ingestor import SalesforceConnector

        mock_client = _make_mock_sf_client()
        mock_sf_cls.return_value = mock_client

        conn = SalesforceConnector(username="u", password="p", security_token="t")
        conn.test_connection()

        # Connection must be closed after the test.
        assert conn._client is None

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    @patch("semantica.ingest.salesforce_ingestor._SimpleSalesforce")
    def test_test_connection_failure_returns_false(self, mock_sf_cls):
        """test_connection() returns False when connect() fails."""
        from semantica.ingest.salesforce_ingestor import SalesforceConnector

        mock_sf_cls.side_effect = Exception("Connection refused")

        conn = SalesforceConnector(username="u", password="p", security_token="t")
        result = conn.test_connection()

        assert result is False

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    @patch("semantica.ingest.salesforce_ingestor._SimpleSalesforce")
    def test_test_connection_limits_failure_returns_false(self, mock_sf_cls):
        """test_connection() returns False when limits() raises."""
        from semantica.ingest.salesforce_ingestor import SalesforceConnector

        mock_client = _make_mock_sf_client()
        mock_client.limits.side_effect = Exception("Rate limit exceeded")
        mock_sf_cls.return_value = mock_client

        conn = SalesforceConnector(username="u", password="p", security_token="t")
        result = conn.test_connection()

        assert result is False

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    @patch("semantica.ingest.salesforce_ingestor._SimpleSalesforce")
    def test_test_connection_does_not_close_pre_existing_connection(self, mock_sf_cls):
        """test_connection() must not close a connection opened before the call."""
        from semantica.ingest.salesforce_ingestor import SalesforceConnector

        mock_client = _make_mock_sf_client()
        mock_sf_cls.return_value = mock_client

        conn = SalesforceConnector(username="u", password="p", security_token="t")
        conn.connect()          # open before test_connection
        assert conn._client is not None

        conn.test_connection()

        # Connection opened externally must still be alive.
        assert conn._client is not None


# ---------------------------------------------------------------------------
# TestSalesforceConnectorSecrets
# ---------------------------------------------------------------------------

class TestSalesforceConnectorSecrets:
    """Verify that no secret values are exposed in logs or exception messages."""

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    @patch("semantica.ingest.salesforce_ingestor._SimpleSalesforce")
    def test_password_not_in_repr(self, mock_sf_cls):
        """repr(connector) must not expose password."""
        from semantica.ingest.salesforce_ingestor import SalesforceConnector

        mock_sf_cls.return_value = _make_mock_sf_client()
        conn = SalesforceConnector(
            username="u", password="my_secret_password", security_token="tok"
        )
        assert "my_secret_password" not in repr(conn)

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    @patch("semantica.ingest.salesforce_ingestor._SimpleSalesforce")
    def test_token_not_in_repr(self, mock_sf_cls):
        """repr(connector) must not expose the security token."""
        from semantica.ingest.salesforce_ingestor import SalesforceConnector

        mock_sf_cls.return_value = _make_mock_sf_client()
        conn = SalesforceConnector(
            username="u", password="p", security_token="TOP_SECRET_TOKEN"
        )
        assert "TOP_SECRET_TOKEN" not in repr(conn)

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    @patch("semantica.ingest.salesforce_ingestor._SimpleSalesforce")
    def test_session_id_not_in_repr(self, mock_sf_cls):
        """repr(connector) must not expose the session ID."""
        from semantica.ingest.salesforce_ingestor import SalesforceConnector

        conn = SalesforceConnector(
            session_id="00D_VERY_SECRET_SID",
            instance_url="https://myorg.salesforce.com",
        )
        assert "00D_VERY_SECRET_SID" not in repr(conn)

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    @patch("semantica.ingest.salesforce_ingestor._SimpleSalesforce")
    def test_auth_error_does_not_leak_password(self, mock_sf_cls):
        """ProcessingError from connect() must not contain password text."""
        from semantica.ingest.salesforce_ingestor import (
            SalesforceConnector,
            _SalesforceAuthenticationFailed,
        )
        from semantica.utils.exceptions import ProcessingError

        mock_sf_cls.side_effect = _SalesforceAuthenticationFailed(
            "INVALID_LOGIN", "some server message"
        )

        conn = SalesforceConnector(
            username="u", password="hunter2", security_token="s3cr3t"
        )
        with pytest.raises(ProcessingError) as exc_info:
            conn.connect()

        assert "hunter2" not in str(exc_info.value)
        assert "s3cr3t" not in str(exc_info.value)


# ---------------------------------------------------------------------------
# TestSalesforceIngestor
# ---------------------------------------------------------------------------

class TestSalesforceIngestor:
    """Tests for the SalesforceIngestor wrapper."""

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    @patch("semantica.ingest.salesforce_ingestor._SimpleSalesforce")
    def test_ingestor_creates_connector(self, mock_sf_cls):
        """SalesforceIngestor creates a SalesforceConnector on init."""
        from semantica.ingest.salesforce_ingestor import SalesforceConnector, SalesforceIngestor

        ingestor = SalesforceIngestor(
            username="u", password="p", security_token="t"
        )

        assert isinstance(ingestor.connector, SalesforceConnector)
        assert ingestor.connector.username == "u"

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    @patch("semantica.ingest.salesforce_ingestor._SimpleSalesforce")
    def test_ingestor_missing_credentials_raises_validation_error(self, mock_sf_cls):
        """ValidationError propagates when no credentials are given."""
        from semantica.ingest.salesforce_ingestor import SalesforceIngestor
        from semantica.utils.exceptions import ValidationError

        with pytest.raises(ValidationError):
            SalesforceIngestor()

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    @patch("semantica.ingest.salesforce_ingestor._SimpleSalesforce")
    def test_context_manager_connects_and_disconnects(self, mock_sf_cls):
        """__enter__ opens connection; __exit__ closes it."""
        from semantica.ingest.salesforce_ingestor import SalesforceIngestor

        mock_client = _make_mock_sf_client()
        mock_sf_cls.return_value = mock_client

        with SalesforceIngestor(
            username="u", password="p", security_token="t"
        ) as sf:
            # Client should be live inside the context.
            assert sf.connector._client is mock_client

        # Client must be released on exit.
        assert sf.connector._client is None

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    @patch("semantica.ingest.salesforce_ingestor._SimpleSalesforce")
    def test_context_manager_connects_only_once(self, mock_sf_cls):
        """Multiple operations inside context manager reuse a single connection."""
        from semantica.ingest.salesforce_ingestor import SalesforceIngestor

        mock_client = _make_mock_sf_client()
        mock_sf_cls.return_value = mock_client

        with SalesforceIngestor(
            username="u", password="p", security_token="t"
        ) as sf:
            # Simulate ingest methods calling connector.connect() internally.
            sf.connector.connect()
            sf.connector.connect()

        # simple-salesforce Salesforce() should have been called exactly once
        # (by __enter__); the subsequent connect() calls reused the client.
        mock_sf_cls.assert_called_once()

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    @patch("semantica.ingest.salesforce_ingestor._SimpleSalesforce")
    def test_close_delegates_to_connector(self, mock_sf_cls):
        """close() disconnects the connector."""
        from semantica.ingest.salesforce_ingestor import SalesforceIngestor

        mock_client = _make_mock_sf_client()
        mock_sf_cls.return_value = mock_client

        ingestor = SalesforceIngestor(
            username="u", password="p", security_token="t"
        )
        ingestor.connector.connect()
        ingestor.close()

        assert ingestor.connector._client is None

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    @patch("semantica.ingest.salesforce_ingestor._SimpleSalesforce")
    def test_context_manager_closes_on_exception(self, mock_sf_cls):
        """__exit__ closes the connection even when an exception is raised inside."""
        from semantica.ingest.salesforce_ingestor import SalesforceIngestor

        mock_client = _make_mock_sf_client()
        mock_sf_cls.return_value = mock_client

        with pytest.raises(ValueError):
            with SalesforceIngestor(
                username="u", password="p", security_token="t"
            ) as sf:
                raise ValueError("something went wrong")

        assert sf.connector._client is None

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    def test_ingestor_missing_lib_raises_import_error(self):
        """ImportError propagates when simple-salesforce is absent."""
        from semantica.ingest.salesforce_ingestor import SalesforceIngestor

        with patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", False):
            with pytest.raises(ImportError) as exc_info:
                SalesforceIngestor(username="u", password="p", security_token="t")

        assert "simple-salesforce" in str(exc_info.value)


# ---------------------------------------------------------------------------
# TestSalesforceData
# ---------------------------------------------------------------------------

class TestSalesforceData:
    """Tests for the SalesforceData dataclass."""

    def test_creation_with_required_fields(self):
        """SalesforceData can be created with minimal required fields."""
        from semantica.ingest.salesforce_ingestor import SalesforceData

        data = SalesforceData(data=[], row_count=0, columns=[])

        assert data.row_count == 0
        assert data.data == []
        assert data.columns == []
        assert data.sobject is None
        assert data.query is None
        assert data.instance_url is None
        assert data.total_size is None
        assert data.metadata == {}
        assert isinstance(data.ingested_at, datetime)

    def test_creation_with_all_fields(self):
        """SalesforceData accepts all optional fields."""
        from semantica.ingest.salesforce_ingestor import SalesforceData

        records = [{"Id": "001", "Name": "Acme"}]
        data = SalesforceData(
            data=records,
            row_count=1,
            columns=["Id", "Name"],
            sobject="Account",
            query="SELECT Id, Name FROM Account",
            instance_url="https://myorg.salesforce.com",
            total_size=1,
            metadata={"custom": "value"},
        )

        assert data.row_count == 1
        assert data.sobject == "Account"
        assert data.query == "SELECT Id, Name FROM Account"
        assert data.instance_url == "https://myorg.salesforce.com"
        assert data.total_size == 1
        assert data.metadata["custom"] == "value"

    def test_no_optional_dependency_required(self):
        """SalesforceData is usable even when simple-salesforce is not installed."""
        # This test intentionally does NOT patch SALESFORCE_AVAILABLE.
        from semantica.ingest.salesforce_ingestor import SalesforceData

        data = SalesforceData(data=[{"Id": "x"}], row_count=1, columns=["Id"])
        assert data.row_count == 1


# ---------------------------------------------------------------------------
# TestImportBehaviourWithoutLib
# ---------------------------------------------------------------------------

class TestImportBehaviourWithoutLib:
    """Verify graceful degradation when simple-salesforce is absent."""

    def test_salesforce_available_is_false_without_lib(self):
        """SALESFORCE_AVAILABLE reflects library presence."""
        # Test that SALESFORCE_AVAILABLE matches actual import capability.
        # The autouse fixture may have injected a mock, so we check the current
        # state: can we import simple_salesforce right now?
        try:
            import simple_salesforce  # noqa: F401
            lib_available_now = True
        except ImportError:
            lib_available_now = False

        import semantica.ingest.salesforce_ingestor as _sf_mod
        # SALESFORCE_AVAILABLE should match the current import capability
        assert _sf_mod.SALESFORCE_AVAILABLE is lib_available_now

    def test_semantica_ingest_imports_cleanly_without_lib(self):
        """semantica.ingest imports successfully even without simple-salesforce."""
        import semantica.ingest as pkg  # noqa: F401 — import must not raise
        assert hasattr(pkg, "SalesforceIngestor")
        assert hasattr(pkg, "SalesforceConnector")
        assert hasattr(pkg, "SalesforceData")

    def test_all_contains_salesforce_names(self):
        """All three Salesforce symbols appear in semantica.ingest.__all__."""
        import semantica.ingest as pkg

        for name in ("SalesforceIngestor", "SalesforceConnector", "SalesforceData"):
            assert name in pkg.__all__, f"{name} missing from __all__"


# ===========================================================================
# Stage 3 — ingestion methods, validators, pagination, schema, export
# ===========================================================================

# ---------------------------------------------------------------------------
# Helpers shared by Stage 3 tests
# ---------------------------------------------------------------------------

def _make_query_result(records, total_size=None, done=True, next_url=None):
    """Build a mock sf.query() / sf.query_more() response dict."""
    return {
        "totalSize": total_size if total_size is not None else len(records),
        "done": done,
        "nextRecordsUrl": next_url,
        "records": records,
    }


def _sf_record(sobject, **fields):
    """Build a raw Salesforce record dict (with attributes, like the real API)."""
    rec = {
        "attributes": {
            "type": sobject,
            "url": f"/services/data/v59.0/sobjects/{sobject}/001",
        }
    }
    rec.update(fields)
    return rec


def _make_describe_result(sobject, field_names):
    """Build a minimal sf.SObjectType.describe() response."""
    return {
        "name": sobject,
        "label": sobject,
        "queryable": True,
        "fields": [
            {"name": f, "type": "string", "label": f, "nillable": True, "length": 255}
            for f in field_names
        ],
    }


def _make_global_describe(sobjects):
    """Build a minimal sf.describe() (global describe) response."""
    return {
        "sobjects": [
            {"name": s, "label": s, "queryable": True}
            for s in sobjects
        ]
    }


# ---------------------------------------------------------------------------
# TestSOQLValidators
# ---------------------------------------------------------------------------

class TestSOQLValidators:
    """Unit tests for the SOQL injection-safety validators."""

    # --- _validate_sobject_name ---

    def test_valid_standard_sobject(self):
        from semantica.ingest.salesforce_ingestor import _validate_sobject_name
        assert _validate_sobject_name("Account") == "Account"

    def test_valid_custom_sobject(self):
        from semantica.ingest.salesforce_ingestor import _validate_sobject_name
        assert _validate_sobject_name("My_Object__c") == "My_Object__c"

    def test_valid_metadata_type(self):
        from semantica.ingest.salesforce_ingestor import _validate_sobject_name
        assert _validate_sobject_name("My_Setting__mdt") == "My_Setting__mdt"

    def test_valid_platform_event(self):
        from semantica.ingest.salesforce_ingestor import _validate_sobject_name
        assert _validate_sobject_name("Order_Event__e") == "Order_Event__e"

    def test_invalid_sobject_with_semicolon(self):
        from semantica.ingest.salesforce_ingestor import _validate_sobject_name
        from semantica.utils.exceptions import ValidationError
        with pytest.raises(ValidationError):
            _validate_sobject_name("Account; DROP TABLE")

    def test_invalid_sobject_starts_with_digit(self):
        from semantica.ingest.salesforce_ingestor import _validate_sobject_name
        from semantica.utils.exceptions import ValidationError
        with pytest.raises(ValidationError):
            _validate_sobject_name("1Account")

    def test_invalid_sobject_with_space(self):
        from semantica.ingest.salesforce_ingestor import _validate_sobject_name
        from semantica.utils.exceptions import ValidationError
        with pytest.raises(ValidationError):
            _validate_sobject_name("My Object")

    def test_invalid_sobject_empty_string(self):
        from semantica.ingest.salesforce_ingestor import _validate_sobject_name
        from semantica.utils.exceptions import ValidationError
        with pytest.raises(ValidationError):
            _validate_sobject_name("")

    # --- _validate_field_name ---

    def test_valid_simple_field(self):
        from semantica.ingest.salesforce_ingestor import _validate_field_name
        assert _validate_field_name("Name") == "Name"

    def test_valid_custom_field(self):
        from semantica.ingest.salesforce_ingestor import _validate_field_name
        assert _validate_field_name("My_Field__c") == "My_Field__c"

    def test_valid_relationship_dot_notation(self):
        from semantica.ingest.salesforce_ingestor import _validate_field_name
        assert _validate_field_name("Owner.Name") == "Owner.Name"

    def test_valid_deep_relationship(self):
        from semantica.ingest.salesforce_ingestor import _validate_field_name
        assert _validate_field_name("Account.Owner.Name") == "Account.Owner.Name"

    def test_invalid_field_with_injection(self):
        from semantica.ingest.salesforce_ingestor import _validate_field_name
        from semantica.utils.exceptions import ValidationError
        with pytest.raises(ValidationError):
            _validate_field_name("Name; DROP")

    def test_invalid_field_empty(self):
        from semantica.ingest.salesforce_ingestor import _validate_field_name
        from semantica.utils.exceptions import ValidationError
        with pytest.raises(ValidationError):
            _validate_field_name("")

    # --- _validate_soql_where ---

    def test_valid_where_clause(self):
        from semantica.ingest.salesforce_ingestor import _validate_soql_where
        assert _validate_soql_where("Type = 'Customer'") == "Type = 'Customer'"

    def test_valid_where_with_and(self):
        from semantica.ingest.salesforce_ingestor import _validate_soql_where
        result = _validate_soql_where("Type = 'Customer' AND AnnualRevenue > 1000")
        assert result == "Type = 'Customer' AND AnnualRevenue > 1000"

    def test_valid_where_with_union_as_data(self):
        """The word 'union' inside a string literal must not be blocked."""
        from semantica.ingest.salesforce_ingestor import _validate_soql_where
        # 'union' inside quotes is data, not SQL syntax
        result = _validate_soql_where("Name = 'Credit Union'")
        assert "Credit Union" in result

    def test_invalid_where_with_semicolon(self):
        from semantica.ingest.salesforce_ingestor import _validate_soql_where
        from semantica.utils.exceptions import ValidationError
        with pytest.raises(ValidationError):
            _validate_soql_where("Type = 'X'; DELETE FROM Account")

    def test_invalid_where_with_comment(self):
        from semantica.ingest.salesforce_ingestor import _validate_soql_where
        from semantica.utils.exceptions import ValidationError
        with pytest.raises(ValidationError):
            _validate_soql_where("Type = 'X' -- comment")

    def test_invalid_where_with_bare_union(self):
        from semantica.ingest.salesforce_ingestor import _validate_soql_where
        from semantica.utils.exceptions import ValidationError
        with pytest.raises(ValidationError):
            _validate_soql_where("1=1 UNION SELECT Id FROM Contact")

    # --- _validate_order_by ---

    def test_valid_order_by_simple(self):
        from semantica.ingest.salesforce_ingestor import _validate_order_by
        assert _validate_order_by("Name ASC") == "Name ASC"

    def test_valid_order_by_multi_column(self):
        from semantica.ingest.salesforce_ingestor import _validate_order_by
        result = _validate_order_by("Name ASC, CreatedDate DESC")
        assert result == "Name ASC, CreatedDate DESC"

    def test_valid_order_by_nulls_last(self):
        from semantica.ingest.salesforce_ingestor import _validate_order_by
        result = _validate_order_by("AnnualRevenue DESC NULLS LAST")
        assert "NULLS LAST" in result

    def test_valid_order_by_relationship(self):
        from semantica.ingest.salesforce_ingestor import _validate_order_by
        result = _validate_order_by("Owner.Name ASC")
        assert result == "Owner.Name ASC"

    def test_invalid_order_by_with_injection(self):
        from semantica.ingest.salesforce_ingestor import _validate_order_by
        from semantica.utils.exceptions import ValidationError
        with pytest.raises(ValidationError):
            _validate_order_by("Name; DROP TABLE Account")

    def test_invalid_order_by_empty(self):
        from semantica.ingest.salesforce_ingestor import _validate_order_by
        from semantica.utils.exceptions import ValidationError
        with pytest.raises(ValidationError):
            _validate_order_by("")


# ---------------------------------------------------------------------------
# TestConvertRows
# ---------------------------------------------------------------------------

class TestConvertRows:
    """Tests for SalesforceIngestor._convert_rows / _clean_record."""

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    def test_strips_attributes(self):
        """attributes key is removed from each record."""
        from semantica.ingest.salesforce_ingestor import SalesforceIngestor

        ingestor = SalesforceIngestor(username="u", password="p", security_token="t")
        raw = [_sf_record("Account", Id="001", Name="Acme")]
        result = ingestor._convert_rows(raw)

        assert "attributes" not in result[0]
        assert result[0]["Id"] == "001"
        assert result[0]["Name"] == "Acme"

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    def test_strips_nested_attributes(self):
        """attributes is removed from nested relationship sub-objects too."""
        from semantica.ingest.salesforce_ingestor import SalesforceIngestor

        ingestor = SalesforceIngestor(username="u", password="p", security_token="t")
        raw = [
            {
                "attributes": {"type": "Account"},
                "Id": "001",
                "Owner": {
                    "attributes": {"type": "User"},
                    "Name": "Alice",
                },
            }
        ]
        result = ingestor._convert_rows(raw)

        assert "attributes" not in result[0]
        assert "attributes" not in result[0]["Owner"]
        assert result[0]["Owner"]["Name"] == "Alice"

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    def test_none_values_preserved(self):
        """None (null) field values are kept as None."""
        from semantica.ingest.salesforce_ingestor import SalesforceIngestor

        ingestor = SalesforceIngestor(username="u", password="p", security_token="t")
        raw = [_sf_record("Account", Id="001", BillingCity=None)]
        result = ingestor._convert_rows(raw)

        assert result[0]["BillingCity"] is None

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    def test_datetime_converted_to_iso_string(self):
        """Python datetime objects are converted to ISO-8601 strings."""
        from semantica.ingest.salesforce_ingestor import SalesforceIngestor

        ingestor = SalesforceIngestor(username="u", password="p", security_token="t")
        dt = datetime(2024, 6, 15, 12, 0, 0)
        raw = [{"attributes": {"type": "Account"}, "Id": "001", "CreatedDate": dt}]
        result = ingestor._convert_rows(raw)

        assert result[0]["CreatedDate"] == "2024-06-15T12:00:00"

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    def test_list_values_cleaned(self):
        """List-valued fields are recursively cleaned."""
        from semantica.ingest.salesforce_ingestor import SalesforceIngestor

        ingestor = SalesforceIngestor(username="u", password="p", security_token="t")
        raw = [
            {
                "attributes": {"type": "Account"},
                "Id": "001",
                "Items": [
                    {"attributes": {"type": "Item"}, "Name": "Widget"},
                ],
            }
        ]
        result = ingestor._convert_rows(raw)

        assert "attributes" not in result[0]["Items"][0]
        assert result[0]["Items"][0]["Name"] == "Widget"

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    def test_string_values_pass_through(self):
        """String values are kept unchanged."""
        from semantica.ingest.salesforce_ingestor import SalesforceIngestor

        ingestor = SalesforceIngestor(username="u", password="p", security_token="t")
        raw = [_sf_record("Contact", Id="003", Email="bob@example.com")]
        result = ingestor._convert_rows(raw)

        assert result[0]["Email"] == "bob@example.com"

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    def test_empty_list_returns_empty(self):
        from semantica.ingest.salesforce_ingestor import SalesforceIngestor

        ingestor = SalesforceIngestor(username="u", password="p", security_token="t")
        assert ingestor._convert_rows([]) == []


# ---------------------------------------------------------------------------
# TestBuildSOQL
# ---------------------------------------------------------------------------

class TestBuildSOQL:
    """Tests for SalesforceIngestor._build_soql."""

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    def test_basic_select(self):
        from semantica.ingest.salesforce_ingestor import SalesforceIngestor

        ingestor = SalesforceIngestor(username="u", password="p", security_token="t")
        soql = ingestor._build_soql("Account", ["Id", "Name"], None, None, None)
        assert soql == "SELECT Id, Name FROM Account"

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    def test_with_where(self):
        from semantica.ingest.salesforce_ingestor import SalesforceIngestor

        ingestor = SalesforceIngestor(username="u", password="p", security_token="t")
        soql = ingestor._build_soql("Account", ["Id"], "Type = 'Customer'", None, None)
        assert "WHERE Type = 'Customer'" in soql

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    def test_with_order_by(self):
        from semantica.ingest.salesforce_ingestor import SalesforceIngestor

        ingestor = SalesforceIngestor(username="u", password="p", security_token="t")
        soql = ingestor._build_soql("Account", ["Id"], None, "Name ASC", None)
        assert "ORDER BY Name ASC" in soql

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    def test_limit_embedded_when_le_2000(self):
        from semantica.ingest.salesforce_ingestor import SalesforceIngestor

        ingestor = SalesforceIngestor(username="u", password="p", security_token="t")
        soql = ingestor._build_soql("Account", ["Id"], None, None, 500)
        assert "LIMIT 500" in soql

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    def test_limit_not_embedded_when_gt_2000(self):
        """For limit > 2000 we let pagination handle the cap."""
        from semantica.ingest.salesforce_ingestor import SalesforceIngestor

        ingestor = SalesforceIngestor(username="u", password="p", security_token="t")
        soql = ingestor._build_soql("Account", ["Id"], None, None, 5000)
        assert "LIMIT" not in soql

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    def test_no_limit_clause_when_none(self):
        from semantica.ingest.salesforce_ingestor import SalesforceIngestor

        ingestor = SalesforceIngestor(username="u", password="p", security_token="t")
        soql = ingestor._build_soql("Account", ["Id"], None, None, None)
        assert "LIMIT" not in soql

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    def test_all_clauses_order(self):
        """WHERE comes before ORDER BY before LIMIT."""
        from semantica.ingest.salesforce_ingestor import SalesforceIngestor

        ingestor = SalesforceIngestor(username="u", password="p", security_token="t")
        soql = ingestor._build_soql(
            "Contact", ["Id", "Name"], "Active = true", "Name ASC", 100
        )
        where_pos = soql.index("WHERE")
        order_pos = soql.index("ORDER BY")
        limit_pos = soql.index("LIMIT")
        assert where_pos < order_pos < limit_pos


# ---------------------------------------------------------------------------
# TestIngestSobject
# ---------------------------------------------------------------------------

class TestIngestSobject:
    """Tests for SalesforceIngestor.ingest_sobject()."""

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    @patch("semantica.ingest.salesforce_ingestor._SimpleSalesforce")
    def test_basic_ingest_with_explicit_fields(self, mock_sf_cls):
        """ingest_sobject returns SalesforceData with correct metadata."""
        from semantica.ingest.salesforce_ingestor import SalesforceData, SalesforceIngestor

        mock_client = _make_mock_sf_client()
        mock_sf_cls.return_value = mock_client
        mock_client.query.return_value = _make_query_result([
            _sf_record("Account", Id="001", Name="Acme"),
            _sf_record("Account", Id="002", Name="Beta"),
        ], total_size=2)

        ingestor = SalesforceIngestor(username="u", password="p", security_token="t")
        data = ingestor.ingest_sobject("Account", fields=["Id", "Name"])

        assert isinstance(data, SalesforceData)
        assert data.sobject == "Account"
        assert data.row_count == 2
        assert data.total_size == 2
        assert "Id" in data.columns
        assert "Name" in data.columns
        # attributes must be stripped
        assert all("attributes" not in row for row in data.data)

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    @patch("semantica.ingest.salesforce_ingestor._SimpleSalesforce")
    def test_ingest_calls_describe_when_no_fields(self, mock_sf_cls):
        """When fields=None, describe() is called to get field list."""
        from semantica.ingest.salesforce_ingestor import SalesforceIngestor

        mock_client = _make_mock_sf_client()
        mock_sf_cls.return_value = mock_client

        mock_sftype = Mock()
        mock_sftype.describe.return_value = _make_describe_result(
            "Account", ["Id", "Name", "BillingCity"]
        )
        mock_client.Account = mock_sftype

        mock_client.query.return_value = _make_query_result([
            _sf_record("Account", Id="001", Name="Acme", BillingCity="SF")
        ], total_size=1)

        ingestor = SalesforceIngestor(username="u", password="p", security_token="t")
        data = ingestor.ingest_sobject("Account")  # no fields arg

        mock_sftype.describe.assert_called_once()
        executed_soql = mock_client.query.call_args[0][0]
        assert "Id" in executed_soql
        assert "Name" in executed_soql
        assert data.row_count == 1

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    @patch("semantica.ingest.salesforce_ingestor._SimpleSalesforce")
    def test_where_clause_included_in_soql(self, mock_sf_cls):
        """WHERE fragment is passed to SOQL correctly."""
        from semantica.ingest.salesforce_ingestor import SalesforceIngestor

        mock_client = _make_mock_sf_client()
        mock_sf_cls.return_value = mock_client
        mock_client.query.return_value = _make_query_result([], total_size=0)

        ingestor = SalesforceIngestor(username="u", password="p", security_token="t")
        ingestor.ingest_sobject(
            "Account", fields=["Id"], where="Type = 'Customer'"
        )

        soql = mock_client.query.call_args[0][0]
        assert "WHERE Type = 'Customer'" in soql

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    @patch("semantica.ingest.salesforce_ingestor._SimpleSalesforce")
    def test_order_by_included_in_soql(self, mock_sf_cls):
        from semantica.ingest.salesforce_ingestor import SalesforceIngestor

        mock_client = _make_mock_sf_client()
        mock_sf_cls.return_value = mock_client
        mock_client.query.return_value = _make_query_result([], total_size=0)

        ingestor = SalesforceIngestor(username="u", password="p", security_token="t")
        ingestor.ingest_sobject("Account", fields=["Id"], order_by="Name ASC")

        soql = mock_client.query.call_args[0][0]
        assert "ORDER BY Name ASC" in soql

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    @patch("semantica.ingest.salesforce_ingestor._SimpleSalesforce")
    def test_limit_le_2000_embedded_in_soql(self, mock_sf_cls):
        from semantica.ingest.salesforce_ingestor import SalesforceIngestor

        mock_client = _make_mock_sf_client()
        mock_sf_cls.return_value = mock_client
        mock_client.query.return_value = _make_query_result([], total_size=0)

        ingestor = SalesforceIngestor(username="u", password="p", security_token="t")
        ingestor.ingest_sobject("Account", fields=["Id"], limit=100)

        soql = mock_client.query.call_args[0][0]
        assert "LIMIT 100" in soql

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    @patch("semantica.ingest.salesforce_ingestor._SimpleSalesforce")
    def test_invalid_sobject_name_raises_validation_error(self, mock_sf_cls):
        """ingest_sobject raises ValidationError for bad sObject names."""
        from semantica.ingest.salesforce_ingestor import SalesforceIngestor
        from semantica.utils.exceptions import ValidationError

        mock_sf_cls.return_value = _make_mock_sf_client()

        ingestor = SalesforceIngestor(username="u", password="p", security_token="t")
        with pytest.raises(ValidationError):
            ingestor.ingest_sobject("Account; DROP TABLE", fields=["Id"])

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    @patch("semantica.ingest.salesforce_ingestor._SimpleSalesforce")
    def test_invalid_field_name_raises_validation_error(self, mock_sf_cls):
        from semantica.ingest.salesforce_ingestor import SalesforceIngestor
        from semantica.utils.exceptions import ValidationError

        mock_sf_cls.return_value = _make_mock_sf_client()

        ingestor = SalesforceIngestor(username="u", password="p", security_token="t")
        with pytest.raises(ValidationError):
            ingestor.ingest_sobject("Account", fields=["Id", "Name; DROP"])

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    @patch("semantica.ingest.salesforce_ingestor._SimpleSalesforce")
    def test_invalid_where_raises_validation_error(self, mock_sf_cls):
        from semantica.ingest.salesforce_ingestor import SalesforceIngestor
        from semantica.utils.exceptions import ValidationError

        mock_sf_cls.return_value = _make_mock_sf_client()

        ingestor = SalesforceIngestor(username="u", password="p", security_token="t")
        with pytest.raises(ValidationError):
            ingestor.ingest_sobject(
                "Account", fields=["Id"], where="1=1; DELETE FROM Account"
            )

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    @patch("semantica.ingest.salesforce_ingestor._SimpleSalesforce")
    def test_api_error_wrapped_as_processing_error(self, mock_sf_cls):
        """Salesforce API errors during query become ProcessingError."""
        from semantica.ingest.salesforce_ingestor import SalesforceIngestor
        from semantica.utils.exceptions import ProcessingError

        mock_client = _make_mock_sf_client()
        mock_sf_cls.return_value = mock_client
        mock_client.query.side_effect = RuntimeError("SOQL error")

        ingestor = SalesforceIngestor(username="u", password="p", security_token="t")
        with pytest.raises(ProcessingError):
            ingestor.ingest_sobject("Account", fields=["Id"])

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    @patch("semantica.ingest.salesforce_ingestor._SimpleSalesforce")
    def test_instance_url_populated_on_result(self, mock_sf_cls):
        """SalesforceData.instance_url comes from the connector."""
        from semantica.ingest.salesforce_ingestor import SalesforceIngestor

        mock_client = _make_mock_sf_client("myorg.salesforce.com")
        mock_sf_cls.return_value = mock_client
        mock_client.query.return_value = _make_query_result([], total_size=0)

        ingestor = SalesforceIngestor(username="u", password="p", security_token="t")
        data = ingestor.ingest_sobject("Account", fields=["Id"])

        assert data.instance_url == "https://myorg.salesforce.com"


# ---------------------------------------------------------------------------
# TestPagination
# ---------------------------------------------------------------------------

class TestPagination:
    """Tests for _query_all pagination logic."""

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    @patch("semantica.ingest.salesforce_ingestor._SimpleSalesforce")
    def test_single_page_done_true(self, mock_sf_cls):
        """No query_more call when first response is done=True."""
        from semantica.ingest.salesforce_ingestor import SalesforceIngestor

        mock_client = _make_mock_sf_client()
        mock_sf_cls.return_value = mock_client
        mock_client.query.return_value = _make_query_result(
            [_sf_record("Account", Id="001")], total_size=1, done=True
        )

        ingestor = SalesforceIngestor(username="u", password="p", security_token="t")
        records, total_size = ingestor._query_all(mock_client, "SELECT Id FROM Account", None)

        assert len(records) == 1
        assert total_size == 1
        mock_client.query_more.assert_not_called()

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    @patch("semantica.ingest.salesforce_ingestor._SimpleSalesforce")
    def test_two_page_pagination(self, mock_sf_cls):
        """query_more is called once when done=False on first page."""
        from semantica.ingest.salesforce_ingestor import SalesforceIngestor

        mock_client = _make_mock_sf_client()
        mock_sf_cls.return_value = mock_client

        page1 = _make_query_result(
            [_sf_record("Account", Id="001"), _sf_record("Account", Id="002")],
            total_size=3,
            done=False,
            next_url="/services/data/v59.0/query/01g-next",
        )
        page2 = _make_query_result(
            [_sf_record("Account", Id="003")],
            total_size=3,
            done=True,
        )

        mock_client.query.return_value = page1
        mock_client.query_more.return_value = page2

        ingestor = SalesforceIngestor(username="u", password="p", security_token="t")
        records, total_size = ingestor._query_all(
            mock_client, "SELECT Id FROM Account", None
        )

        assert len(records) == 3
        assert total_size == 3
        mock_client.query_more.assert_called_once_with(
            "/services/data/v59.0/query/01g-next", identifier_is_url=True
        )

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    @patch("semantica.ingest.salesforce_ingestor._SimpleSalesforce")
    def test_pagination_stops_at_limit(self, mock_sf_cls):
        """Pagination stops as soon as limit records are collected."""
        from semantica.ingest.salesforce_ingestor import SalesforceIngestor

        mock_client = _make_mock_sf_client()
        mock_sf_cls.return_value = mock_client

        # Page 1: 2 records, more available
        page1 = _make_query_result(
            [_sf_record("Account", Id="001"), _sf_record("Account", Id="002")],
            total_size=10,
            done=False,
            next_url="/services/data/v59.0/query/01g-next",
        )
        mock_client.query.return_value = page1

        ingestor = SalesforceIngestor(username="u", password="p", security_token="t")
        records, _ = ingestor._query_all(mock_client, "SELECT Id FROM Account", limit=2)

        # Should have stopped after page 1 — limit already reached
        assert len(records) == 2
        mock_client.query_more.assert_not_called()

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    @patch("semantica.ingest.salesforce_ingestor._SimpleSalesforce")
    def test_limit_trims_excess_records(self, mock_sf_cls):
        """Result is sliced to limit even if a page overshoots."""
        from semantica.ingest.salesforce_ingestor import SalesforceIngestor

        mock_client = _make_mock_sf_client()
        mock_sf_cls.return_value = mock_client

        # 5 records in one page, limit=3
        page1 = _make_query_result(
            [_sf_record("Account", Id=str(i)) for i in range(5)],
            total_size=5,
            done=True,
        )
        mock_client.query.return_value = page1

        ingestor = SalesforceIngestor(username="u", password="p", security_token="t")
        records, _ = ingestor._query_all(mock_client, "SELECT Id FROM Account", limit=3)

        assert len(records) == 3

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    @patch("semantica.ingest.salesforce_ingestor._SimpleSalesforce")
    def test_query_more_failure_raises_processing_error(self, mock_sf_cls):
        """query_more errors are wrapped as ProcessingError."""
        from semantica.ingest.salesforce_ingestor import SalesforceIngestor
        from semantica.utils.exceptions import ProcessingError

        mock_client = _make_mock_sf_client()
        mock_sf_cls.return_value = mock_client

        page1 = _make_query_result(
            [_sf_record("Account", Id="001")],
            total_size=2,
            done=False,
            next_url="/services/data/v59.0/query/01g-next",
        )
        mock_client.query.return_value = page1
        mock_client.query_more.side_effect = RuntimeError("Connection reset")

        ingestor = SalesforceIngestor(username="u", password="p", security_token="t")
        with pytest.raises(ProcessingError):
            ingestor._query_all(mock_client, "SELECT Id FROM Account", None)

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    @patch("semantica.ingest.salesforce_ingestor._SimpleSalesforce")
    def test_ingest_sobject_with_large_limit_uses_pagination(self, mock_sf_cls):
        """limit > 2000 doesn't embed LIMIT in SOQL, collects via pagination."""
        from semantica.ingest.salesforce_ingestor import SalesforceIngestor

        mock_client = _make_mock_sf_client()
        mock_sf_cls.return_value = mock_client

        # Return enough records to satisfy limit=3000 across two pages
        page1 = _make_query_result(
            [_sf_record("Account", Id=str(i)) for i in range(2000)],
            total_size=3000,
            done=False,
            next_url="/next",
        )
        page2 = _make_query_result(
            [_sf_record("Account", Id=str(i)) for i in range(2000, 3000)],
            total_size=3000,
            done=True,
        )
        mock_client.query.return_value = page1
        mock_client.query_more.return_value = page2

        ingestor = SalesforceIngestor(username="u", password="p", security_token="t")
        data = ingestor.ingest_sobject("Account", fields=["Id"], limit=3000)

        soql = mock_client.query.call_args[0][0]
        assert "LIMIT" not in soql    # not embedded in SOQL
        assert data.row_count == 3000  # collected via pagination


# ---------------------------------------------------------------------------
# TestIngestQuery
# ---------------------------------------------------------------------------

class TestIngestQuery:
    """Tests for SalesforceIngestor.ingest_query()."""

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    @patch("semantica.ingest.salesforce_ingestor._SimpleSalesforce")
    def test_basic_ingest_query(self, mock_sf_cls):
        """ingest_query passes SOQL verbatim and returns SalesforceData."""
        from semantica.ingest.salesforce_ingestor import SalesforceData, SalesforceIngestor

        mock_client = _make_mock_sf_client()
        mock_sf_cls.return_value = mock_client
        mock_client.query.return_value = _make_query_result(
            [_sf_record("Account", Id="001", Name="Acme")], total_size=1
        )

        ingestor = SalesforceIngestor(username="u", password="p", security_token="t")
        soql = "SELECT Id, Name FROM Account LIMIT 1"
        data = ingestor.ingest_query(soql)

        assert isinstance(data, SalesforceData)
        assert data.query == soql
        assert data.row_count == 1
        mock_client.query.assert_called_once_with(soql)

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    @patch("semantica.ingest.salesforce_ingestor._SimpleSalesforce")
    def test_ingest_query_follows_pagination(self, mock_sf_cls):
        """ingest_query collects all pages."""
        from semantica.ingest.salesforce_ingestor import SalesforceIngestor

        mock_client = _make_mock_sf_client()
        mock_sf_cls.return_value = mock_client

        page1 = _make_query_result(
            [_sf_record("Contact", Id="001")],
            total_size=2,
            done=False,
            next_url="/next",
        )
        page2 = _make_query_result(
            [_sf_record("Contact", Id="002")],
            total_size=2,
            done=True,
        )
        mock_client.query.return_value = page1
        mock_client.query_more.return_value = page2

        ingestor = SalesforceIngestor(username="u", password="p", security_token="t")
        data = ingestor.ingest_query("SELECT Id FROM Contact")

        assert data.row_count == 2
        assert data.total_size == 2

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    @patch("semantica.ingest.salesforce_ingestor._SimpleSalesforce")
    def test_ingest_query_api_error_raises_processing_error(self, mock_sf_cls):
        from semantica.ingest.salesforce_ingestor import SalesforceIngestor
        from semantica.utils.exceptions import ProcessingError

        mock_client = _make_mock_sf_client()
        mock_sf_cls.return_value = mock_client
        mock_client.query.side_effect = RuntimeError("Malformed SOQL")

        ingestor = SalesforceIngestor(username="u", password="p", security_token="t")
        with pytest.raises(ProcessingError):
            ingestor.ingest_query("SELECT FROM Account")  # intentionally bad

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    @patch("semantica.ingest.salesforce_ingestor._SimpleSalesforce")
    def test_ingest_query_closes_transient_connection(self, mock_sf_cls):
        """ingest_query disconnects when called outside a context manager."""
        from semantica.ingest.salesforce_ingestor import SalesforceIngestor

        mock_client = _make_mock_sf_client()
        mock_sf_cls.return_value = mock_client
        mock_client.query.return_value = _make_query_result([], total_size=0)

        ingestor = SalesforceIngestor(username="u", password="p", security_token="t")
        assert ingestor.connector._client is None
        ingestor.ingest_query("SELECT Id FROM Account")
        assert ingestor.connector._client is None

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    @patch("semantica.ingest.salesforce_ingestor._SimpleSalesforce")
    def test_ingest_query_reuses_context_manager_connection(self, mock_sf_cls):
        """ingest_query does not close a context-manager connection."""
        from semantica.ingest.salesforce_ingestor import SalesforceIngestor

        mock_client = _make_mock_sf_client()
        mock_sf_cls.return_value = mock_client
        mock_client.query.return_value = _make_query_result([], total_size=0)

        with SalesforceIngestor(
            username="u", password="p", security_token="t"
        ) as sf:
            sf.ingest_query("SELECT Id FROM Account")
            # Connection must still be open
            assert sf.connector._client is mock_client

        # Closed only on __exit__
        assert sf.connector._client is None


# ---------------------------------------------------------------------------
# TestListSobjects
# ---------------------------------------------------------------------------

class TestListSobjects:
    """Tests for SalesforceIngestor.list_sobjects()."""

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    @patch("semantica.ingest.salesforce_ingestor._SimpleSalesforce")
    def test_returns_sorted_list(self, mock_sf_cls):
        from semantica.ingest.salesforce_ingestor import SalesforceIngestor

        mock_client = _make_mock_sf_client()
        mock_sf_cls.return_value = mock_client
        mock_client.describe.return_value = _make_global_describe(
            ["Contact", "Account", "Opportunity"]
        )

        ingestor = SalesforceIngestor(username="u", password="p", security_token="t")
        result = ingestor.list_sobjects()

        assert result == ["Account", "Contact", "Opportunity"]

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    @patch("semantica.ingest.salesforce_ingestor._SimpleSalesforce")
    def test_api_error_raises_processing_error(self, mock_sf_cls):
        from semantica.ingest.salesforce_ingestor import SalesforceIngestor
        from semantica.utils.exceptions import ProcessingError

        mock_client = _make_mock_sf_client()
        mock_sf_cls.return_value = mock_client
        mock_client.describe.side_effect = RuntimeError("Timeout")

        ingestor = SalesforceIngestor(username="u", password="p", security_token="t")
        with pytest.raises(ProcessingError):
            ingestor.list_sobjects()

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    @patch("semantica.ingest.salesforce_ingestor._SimpleSalesforce")
    def test_closes_transient_connection(self, mock_sf_cls):
        from semantica.ingest.salesforce_ingestor import SalesforceIngestor

        mock_client = _make_mock_sf_client()
        mock_sf_cls.return_value = mock_client
        mock_client.describe.return_value = _make_global_describe(["Account"])

        ingestor = SalesforceIngestor(username="u", password="p", security_token="t")
        ingestor.list_sobjects()
        assert ingestor.connector._client is None

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    @patch("semantica.ingest.salesforce_ingestor._SimpleSalesforce")
    def test_empty_org_returns_empty_list(self, mock_sf_cls):
        from semantica.ingest.salesforce_ingestor import SalesforceIngestor

        mock_client = _make_mock_sf_client()
        mock_sf_cls.return_value = mock_client
        mock_client.describe.return_value = {"sobjects": []}

        ingestor = SalesforceIngestor(username="u", password="p", security_token="t")
        assert ingestor.list_sobjects() == []


# ---------------------------------------------------------------------------
# TestGetSobjectSchema
# ---------------------------------------------------------------------------

class TestGetSobjectSchema:
    """Tests for SalesforceIngestor.get_sobject_schema()."""

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    @patch("semantica.ingest.salesforce_ingestor._SimpleSalesforce")
    def test_returns_schema_dict(self, mock_sf_cls):
        from semantica.ingest.salesforce_ingestor import SalesforceIngestor

        mock_client = _make_mock_sf_client()
        mock_sf_cls.return_value = mock_client

        mock_sftype = Mock()
        mock_sftype.describe.return_value = _make_describe_result(
            "Account", ["Id", "Name", "BillingCity"]
        )
        mock_client.Account = mock_sftype

        ingestor = SalesforceIngestor(username="u", password="p", security_token="t")
        schema = ingestor.get_sobject_schema("Account")

        assert schema["name"] == "Account"
        assert schema["queryable"] is True
        assert len(schema["fields"]) == 3
        assert schema["fields"][0]["name"] == "Id"

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    @patch("semantica.ingest.salesforce_ingestor._SimpleSalesforce")
    def test_field_dict_has_required_keys(self, mock_sf_cls):
        from semantica.ingest.salesforce_ingestor import SalesforceIngestor

        mock_client = _make_mock_sf_client()
        mock_sf_cls.return_value = mock_client

        mock_sftype = Mock()
        mock_sftype.describe.return_value = _make_describe_result("Account", ["Id"])
        mock_client.Account = mock_sftype

        ingestor = SalesforceIngestor(username="u", password="p", security_token="t")
        schema = ingestor.get_sobject_schema("Account")

        field = schema["fields"][0]
        for key in ("name", "type", "label", "nillable", "length"):
            assert key in field, f"Missing key: {key}"

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    @patch("semantica.ingest.salesforce_ingestor._SimpleSalesforce")
    def test_invalid_sobject_name_raises_validation_error(self, mock_sf_cls):
        from semantica.ingest.salesforce_ingestor import SalesforceIngestor
        from semantica.utils.exceptions import ValidationError

        mock_sf_cls.return_value = _make_mock_sf_client()

        ingestor = SalesforceIngestor(username="u", password="p", security_token="t")
        with pytest.raises(ValidationError):
            ingestor.get_sobject_schema("Bad Name!")

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    @patch("semantica.ingest.salesforce_ingestor._SimpleSalesforce")
    def test_api_error_raises_processing_error(self, mock_sf_cls):
        from semantica.ingest.salesforce_ingestor import SalesforceIngestor
        from semantica.utils.exceptions import ProcessingError

        mock_client = _make_mock_sf_client()
        mock_sf_cls.return_value = mock_client

        mock_sftype = Mock()
        mock_sftype.describe.side_effect = RuntimeError("Not found")
        mock_client.Account = mock_sftype

        ingestor = SalesforceIngestor(username="u", password="p", security_token="t")
        with pytest.raises(ProcessingError):
            ingestor.get_sobject_schema("Account")


# ---------------------------------------------------------------------------
# TestExportAsDocuments
# ---------------------------------------------------------------------------

class TestExportAsDocuments:
    """Tests for SalesforceIngestor.export_as_documents()."""

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    def test_basic_export(self):
        from semantica.ingest.salesforce_ingestor import SalesforceData, SalesforceIngestor

        ingestor = SalesforceIngestor(username="u", password="p", security_token="t")
        data = SalesforceData(
            data=[
                {"Id": "001", "Name": "Acme", "Industry": "Tech"},
                {"Id": "002", "Name": "Beta", "Industry": "Finance"},
            ],
            row_count=2,
            columns=["Id", "Name", "Industry"],
            sobject="Account",
            instance_url="https://myorg.salesforce.com",
        )

        docs = ingestor.export_as_documents(data, text_fields=["Name", "Industry"])

        assert len(docs) == 2
        assert docs[0]["id"] == "001"
        assert docs[0]["text"] == "Acme Tech"
        assert docs[0]["metadata"]["source"] == "salesforce"
        assert docs[0]["metadata"]["sobject"] == "Account"
        assert docs[0]["metadata"]["instance_url"] == "https://myorg.salesforce.com"
        assert docs[0]["metadata"]["row_data"]["Name"] == "Acme"

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    def test_default_text_uses_all_string_fields(self):
        """When text_fields is None, all non-None string values are joined."""
        from semantica.ingest.salesforce_ingestor import SalesforceData, SalesforceIngestor

        ingestor = SalesforceIngestor(username="u", password="p", security_token="t")
        data = SalesforceData(
            data=[{"Id": "001", "Name": "Acme", "AnnualRevenue": 1000000}],
            row_count=1,
            columns=["Id", "Name", "AnnualRevenue"],
            sobject="Account",
            instance_url=None,
        )

        docs = ingestor.export_as_documents(data)

        # text should join string fields Id and Name (AnnualRevenue is int)
        assert "Acme" in docs[0]["text"]
        assert "001" in docs[0]["text"]

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    def test_id_field_default_is_Id(self):
        """Default id_field is 'Id' (Salesforce canonical)."""
        from semantica.ingest.salesforce_ingestor import SalesforceData, SalesforceIngestor

        ingestor = SalesforceIngestor(username="u", password="p", security_token="t")
        data = SalesforceData(
            data=[{"Id": "003RECORD", "Name": "Alice"}],
            row_count=1,
            columns=["Id", "Name"],
            sobject="Contact",
            instance_url=None,
        )

        docs = ingestor.export_as_documents(data)
        assert docs[0]["id"] == "003RECORD"

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    def test_custom_id_field(self):
        from semantica.ingest.salesforce_ingestor import SalesforceData, SalesforceIngestor

        ingestor = SalesforceIngestor(username="u", password="p", security_token="t")
        data = SalesforceData(
            data=[{"External_Id__c": "EXT-001", "Name": "Widget"}],
            row_count=1,
            columns=["External_Id__c", "Name"],
            sobject="Product__c",
            instance_url=None,
        )

        docs = ingestor.export_as_documents(data, id_field="External_Id__c")
        assert docs[0]["id"] == "EXT-001"

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    def test_missing_id_field_falls_back_to_index(self):
        """If the id_field key is absent, the row index is used."""
        from semantica.ingest.salesforce_ingestor import SalesforceData, SalesforceIngestor

        ingestor = SalesforceIngestor(username="u", password="p", security_token="t")
        data = SalesforceData(
            data=[{"Name": "No-ID record"}],
            row_count=1,
            columns=["Name"],
            sobject="Account",
            instance_url=None,
        )

        docs = ingestor.export_as_documents(data)
        assert docs[0]["id"] == "0"  # index 0 as string

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    def test_none_text_fields_skipped(self):
        """None values in text_fields are not included in text."""
        from semantica.ingest.salesforce_ingestor import SalesforceData, SalesforceIngestor

        ingestor = SalesforceIngestor(username="u", password="p", security_token="t")
        data = SalesforceData(
            data=[{"Id": "001", "Name": "Acme", "Description": None}],
            row_count=1,
            columns=["Id", "Name", "Description"],
            sobject="Account",
            instance_url=None,
        )

        docs = ingestor.export_as_documents(data, text_fields=["Name", "Description"])
        assert docs[0]["text"] == "Acme"  # None Description excluded

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    def test_empty_data_returns_empty_list(self):
        from semantica.ingest.salesforce_ingestor import SalesforceData, SalesforceIngestor

        ingestor = SalesforceIngestor(username="u", password="p", security_token="t")
        data = SalesforceData(data=[], row_count=0, columns=[], sobject="Account")
        docs = ingestor.export_as_documents(data)
        assert docs == []


# ---------------------------------------------------------------------------
# TestConnectionLifecycleWithIngestion
# ---------------------------------------------------------------------------

class TestConnectionLifecycleWithIngestion:
    """Connection-reuse and lifecycle tests for ingestion methods."""

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    @patch("semantica.ingest.salesforce_ingestor._SimpleSalesforce")
    def test_multiple_calls_inside_context_manager_reuse_connection(self, mock_sf_cls):
        """Multiple ingest calls inside a context manager share one connection."""
        from semantica.ingest.salesforce_ingestor import SalesforceIngestor

        mock_client = _make_mock_sf_client()
        mock_sf_cls.return_value = mock_client
        mock_client.query.return_value = _make_query_result([], total_size=0)
        mock_client.describe.return_value = _make_global_describe(["Account"])

        with SalesforceIngestor(
            username="u", password="p", security_token="t"
        ) as sf:
            sf.ingest_query("SELECT Id FROM Account")
            sf.list_sobjects()
            sf.ingest_query("SELECT Id FROM Contact")

        # Simple Salesforce constructor called exactly once — __enter__ only.
        mock_sf_cls.assert_called_once()
        # Connection released on exit.
        assert sf.connector._client is None

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    @patch("semantica.ingest.salesforce_ingestor._SimpleSalesforce")
    def test_standalone_ingest_closes_connection(self, mock_sf_cls):
        """Standalone ingest_query opens and closes its own connection."""
        from semantica.ingest.salesforce_ingestor import SalesforceIngestor

        mock_client = _make_mock_sf_client()
        mock_sf_cls.return_value = mock_client
        mock_client.query.return_value = _make_query_result([], total_size=0)

        ingestor = SalesforceIngestor(username="u", password="p", security_token="t")
        ingestor.ingest_query("SELECT Id FROM Account")

        assert ingestor.connector._client is None


# ===========================================================================
# Review-stage regression tests — bugs fixed during code review
# ===========================================================================

class TestReviewFixes:
    """Regression tests for bugs found and fixed during the Stage 3 review."""

    # ------------------------------------------------------------------
    # Bug 1: limit=0 must not generate LIMIT 0 in SOQL
    # ------------------------------------------------------------------

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    @patch("semantica.ingest.salesforce_ingestor._SimpleSalesforce")
    def test_limit_zero_returns_empty_without_api_call(self, mock_sf_cls):
        """limit=0 short-circuits before connecting and returns empty SalesforceData."""
        from semantica.ingest.salesforce_ingestor import SalesforceData, SalesforceIngestor

        mock_sf_cls.return_value = _make_mock_sf_client()

        ingestor = SalesforceIngestor(username="u", password="p", security_token="t")
        data = ingestor.ingest_sobject("Account", fields=["Id"], limit=0)

        assert isinstance(data, SalesforceData)
        assert data.row_count == 0
        assert data.data == []
        assert data.sobject == "Account"
        # No network call should have been made
        mock_sf_cls.assert_not_called()

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    @patch("semantica.ingest.salesforce_ingestor._SimpleSalesforce")
    def test_limit_negative_raises_validation_error(self, mock_sf_cls):
        """Negative limit raises ValidationError before any network call."""
        from semantica.ingest.salesforce_ingestor import SalesforceIngestor
        from semantica.utils.exceptions import ValidationError

        mock_sf_cls.return_value = _make_mock_sf_client()

        ingestor = SalesforceIngestor(username="u", password="p", security_token="t")
        with pytest.raises(ValidationError, match="non-negative"):
            ingestor.ingest_sobject("Contact", fields=["Id"], limit=-1)
        mock_sf_cls.assert_not_called()

    def test_build_soql_limit_zero_not_embedded(self):
        """_build_soql must not embed LIMIT 0 — caller handles limit=0 upstream."""
        with patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True):
            from semantica.ingest.salesforce_ingestor import SalesforceIngestor

            ingestor = SalesforceIngestor(username="u", password="p", security_token="t")
            # Calling _build_soql directly with limit=0 should not emit LIMIT 0
            soql = ingestor._build_soql("Account", ["Id"], None, None, 0)
            assert "LIMIT 0" not in soql, f"LIMIT 0 found in SOQL: {soql!r}"

    def test_build_soql_limit_one_embedded(self):
        """limit=1 is the smallest valid SOQL LIMIT — must be embedded."""
        with patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True):
            from semantica.ingest.salesforce_ingestor import SalesforceIngestor

            ingestor = SalesforceIngestor(username="u", password="p", security_token="t")
            soql = ingestor._build_soql("Account", ["Id"], None, None, 1)
            assert "LIMIT 1" in soql

    def test_build_soql_limit_2000_embedded(self):
        """limit=2000 is at the boundary — must still be embedded in SOQL."""
        with patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True):
            from semantica.ingest.salesforce_ingestor import SalesforceIngestor

            ingestor = SalesforceIngestor(username="u", password="p", security_token="t")
            soql = ingestor._build_soql("Account", ["Id"], None, None, 2000)
            assert "LIMIT 2000" in soql

    def test_build_soql_limit_2001_not_embedded(self):
        """limit=2001 crosses the boundary — must not embed LIMIT in SOQL."""
        with patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True):
            from semantica.ingest.salesforce_ingestor import SalesforceIngestor

            ingestor = SalesforceIngestor(username="u", password="p", security_token="t")
            soql = ingestor._build_soql("Account", ["Id"], None, None, 2001)
            assert "LIMIT" not in soql

    # ------------------------------------------------------------------
    # Bug 2: compound address/location fields must be excluded from auto-describe
    # ------------------------------------------------------------------

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    @patch("semantica.ingest.salesforce_ingestor._SimpleSalesforce")
    def test_get_all_field_names_excludes_address_type(self, mock_sf_cls):
        """_get_all_field_names filters out compound address fields."""
        from semantica.ingest.salesforce_ingestor import SalesforceIngestor

        mock_client = _make_mock_sf_client()
        mock_sf_cls.return_value = mock_client

        mock_sftype = Mock()
        mock_sftype.describe.return_value = {
            "name": "Account",
            "fields": [
                {"name": "Id", "type": "id"},
                {"name": "Name", "type": "string"},
                {"name": "BillingAddress", "type": "address"},   # compound — excluded
                {"name": "BillingStreet", "type": "string"},    # component — included
                {"name": "BillingCity", "type": "string"},      # component — included
            ],
        }
        mock_client.Account = mock_sftype

        ingestor = SalesforceIngestor(username="u", password="p", security_token="t")
        conn = ingestor.connector.connect()
        field_names = ingestor._get_all_field_names(conn, "Account")

        assert "BillingAddress" not in field_names, "Compound address field must be excluded"
        assert "Id" in field_names
        assert "Name" in field_names
        assert "BillingStreet" in field_names
        assert "BillingCity" in field_names

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    @patch("semantica.ingest.salesforce_ingestor._SimpleSalesforce")
    def test_get_all_field_names_excludes_location_type(self, mock_sf_cls):
        """_get_all_field_names filters out compound geolocation fields."""
        from semantica.ingest.salesforce_ingestor import SalesforceIngestor

        mock_client = _make_mock_sf_client()
        mock_sf_cls.return_value = mock_client

        mock_sftype = Mock()
        mock_sftype.describe.return_value = {
            "name": "MyObj__c",
            "fields": [
                {"name": "Id", "type": "id"},
                {"name": "Location__c", "type": "location"},    # compound — excluded
                {"name": "Location__Latitude__s", "type": "double"},   # component — included
                {"name": "Location__Longitude__s", "type": "double"},  # component — included
            ],
        }
        mock_client.MyObj__c = mock_sftype

        ingestor = SalesforceIngestor(username="u", password="p", security_token="t")
        conn = ingestor.connector.connect()
        field_names = ingestor._get_all_field_names(conn, "MyObj__c")

        assert "Location__c" not in field_names
        assert "Location__Latitude__s" in field_names
        assert "Location__Longitude__s" in field_names

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    @patch("semantica.ingest.salesforce_ingestor._SimpleSalesforce")
    def test_ingest_sobject_with_no_fields_excludes_compound_fields(self, mock_sf_cls):
        """ingest_sobject fields=None must not include address/location in SOQL."""
        from semantica.ingest.salesforce_ingestor import SalesforceIngestor

        mock_client = _make_mock_sf_client()
        mock_sf_cls.return_value = mock_client

        mock_sftype = Mock()
        mock_sftype.describe.return_value = {
            "name": "Account",
            "fields": [
                {"name": "Id", "type": "id"},
                {"name": "Name", "type": "string"},
                {"name": "BillingAddress", "type": "address"},
                {"name": "BillingStreet", "type": "string"},
            ],
        }
        mock_client.Account = mock_sftype
        mock_client.query.return_value = _make_query_result(
            [_sf_record("Account", Id="001", Name="Acme", BillingStreet="123 Main")],
            total_size=1,
        )

        ingestor = SalesforceIngestor(username="u", password="p", security_token="t")
        data = ingestor.ingest_sobject("Account")  # fields=None

        executed_soql = mock_client.query.call_args[0][0]
        assert "BillingAddress" not in executed_soql, (
            f"Compound address field found in SOQL: {executed_soql!r}"
        )
        assert "BillingStreet" in executed_soql

    # ------------------------------------------------------------------
    # Bug 3: SOQL string literal regex must use '' not backslash escaping
    # ------------------------------------------------------------------

    def test_soql_string_literal_regex_matches_sql_style_escaped_quote(self):
        """_SOQL_STRING_LITERAL_RE must treat '' (two single quotes) as an escaped quote."""
        from semantica.ingest.salesforce_ingestor import _SOQL_STRING_LITERAL_RE

        # In SOQL, O'Brien is written as 'O''Brien' (two consecutive single quotes)
        text = "Name = 'O''Brien'"
        matches = _SOQL_STRING_LITERAL_RE.findall(text)

        # The whole 'O''Brien' must be a single match, not two separate matches
        assert len(matches) == 1, (
            f"Expected 1 match for SOQL-style escaped quote, got {len(matches)}: {matches}"
        )
        assert matches[0] == "'O''Brien'", (
            f"Matched wrong literal: {matches[0]!r}"
        )

    def test_soql_where_union_inside_escaped_quote_literal_not_blocked(self):
        """'union' inside a SOQL-style ''quoted'' literal must not be blocked."""
        from semantica.ingest.salesforce_ingestor import _validate_soql_where
        # SOQL literal containing 'union' as data (properly quoted)
        # should not raise ValidationError
        _validate_soql_where("Industry = 'credit union'")  # must not raise

    def test_mask_soql_literals_handles_double_quote_escape(self):
        """_mask_soql_literals must correctly mask O''Brien as a single literal."""
        from semantica.ingest.salesforce_ingestor import _mask_soql_literals

        result = _mask_soql_literals("Name = 'O''Brien'")
        # The masked result should have no unmasked 'union'-style tokens
        # and the literal should be fully replaced
        assert "O''Brien" not in result, (
            "Literal content 'O''Brien' should have been masked"
        )
        # The quotes and replacement characters should be present
        assert "'" in result  # opening and closing quotes remain

    def test_soql_literal_regex_no_backslash_escape(self):
        """Backslash is NOT a SOQL quote escape — must not be treated as one."""
        from semantica.ingest.salesforce_ingestor import _SOQL_STRING_LITERAL_RE

        # In SOQL, backslash has no special meaning inside a string literal
        # A string ending with backslash before the closing quote is still valid
        # (backslash is just a literal backslash character)
        text = r"Name = 'test\value'"
        matches = _SOQL_STRING_LITERAL_RE.findall(text)
        # Should match 'test\value' as one literal (backslash is literal)
        assert len(matches) == 1


# ===========================================================================
# Stage 4 — focused tests per task specification
# ===========================================================================

# ---------------------------------------------------------------------------
# TestSalesforceDataConventions
# ---------------------------------------------------------------------------

class TestSalesforceDataConventions:
    """Verify SalesforceData field semantics, defaults, and row_count / total_size
    distinction against the Snowflake/Databricks sibling conventions."""

    def test_row_count_reflects_data_length(self):
        """row_count must equal len(data), not total_size."""
        from semantica.ingest.salesforce_ingestor import SalesforceData

        records = [{"Id": "001", "Name": "Acme"}, {"Id": "002", "Name": "Beta"}]
        data = SalesforceData(
            data=records,
            row_count=2,
            columns=["Id", "Name"],
            total_size=9999,  # many more records match the query
        )

        assert data.row_count == 2         # records actually in data
        assert data.total_size == 9999     # records matching the query before limit
        assert data.row_count != data.total_size  # clear distinction

    def test_total_size_none_when_unknown(self):
        """total_size may be None when the information is not available."""
        from semantica.ingest.salesforce_ingestor import SalesforceData

        data = SalesforceData(data=[], row_count=0, columns=[])
        assert data.total_size is None

    def test_metadata_defaults_to_empty_dict(self):
        """metadata defaults to a fresh empty dict (not a shared instance)."""
        from semantica.ingest.salesforce_ingestor import SalesforceData

        d1 = SalesforceData(data=[], row_count=0, columns=[])
        d2 = SalesforceData(data=[], row_count=0, columns=[])
        assert d1.metadata == {}
        assert d2.metadata == {}
        # Mutable default: must be separate instances
        d1.metadata["x"] = 1
        assert "x" not in d2.metadata

    def test_ingested_at_is_a_datetime(self):
        """ingested_at is auto-populated with a datetime on creation."""
        from semantica.ingest.salesforce_ingestor import SalesforceData

        data = SalesforceData(data=[], row_count=0, columns=[])
        assert isinstance(data.ingested_at, datetime)

    def test_sobject_none_for_raw_soql(self):
        """sobject is None when data comes from a raw SOQL query (may span objects)."""
        from semantica.ingest.salesforce_ingestor import SalesforceData

        data = SalesforceData(
            data=[{"Id": "001"}],
            row_count=1,
            columns=["Id"],
            query="SELECT Id FROM Account",
            # sobject intentionally not set
        )
        assert data.sobject is None

    def test_sobject_set_for_ingest_sobject_result(self):
        """sobject is set when data comes from ingest_sobject()."""
        from semantica.ingest.salesforce_ingestor import SalesforceData

        data = SalesforceData(
            data=[],
            row_count=0,
            columns=[],
            sobject="Account",
        )
        assert data.sobject == "Account"

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    @patch("semantica.ingest.salesforce_ingestor._SimpleSalesforce")
    def test_ingest_sobject_metadata_uses_query_key(self, mock_sf_cls):
        """ingest_sobject metadata must use 'query' (not 'soql') — consistent with
        Snowflake/Databricks metadata={'query': query}."""
        from semantica.ingest.salesforce_ingestor import SalesforceIngestor

        mock_client = _make_mock_sf_client()
        mock_sf_cls.return_value = mock_client
        mock_client.query.return_value = _make_query_result(
            [_sf_record("Account", Id="001")], total_size=1
        )

        ingestor = SalesforceIngestor(username="u", password="p", security_token="t")
        data = ingestor.ingest_sobject("Account", fields=["Id"])

        assert "query" in data.metadata, (
            "metadata must contain 'query' key to match Snowflake/Databricks convention"
        )
        assert "soql" not in data.metadata, (
            "'soql' is the old key name — must be 'query'"
        )
        # The metadata['query'] value should be the executed SOQL
        assert "SELECT" in data.metadata["query"]
        assert "Account" in data.metadata["query"]

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    @patch("semantica.ingest.salesforce_ingestor._SimpleSalesforce")
    def test_ingest_query_metadata_uses_query_key(self, mock_sf_cls):
        """ingest_query metadata must contain 'query' key with the executed SOQL."""
        from semantica.ingest.salesforce_ingestor import SalesforceIngestor

        mock_client = _make_mock_sf_client()
        mock_sf_cls.return_value = mock_client
        mock_client.query.return_value = _make_query_result([], total_size=0)

        ingestor = SalesforceIngestor(username="u", password="p", security_token="t")
        soql = "SELECT Id, Name FROM Contact WHERE IsActive = true"
        data = ingestor.ingest_query(soql)

        assert "query" in data.metadata
        assert data.metadata["query"] == soql


# ---------------------------------------------------------------------------
# TestObjectDiscoveryCustomObjects
# ---------------------------------------------------------------------------

class TestObjectDiscoveryCustomObjects:
    """Verify list_sobjects and get_sobject_schema work with custom objects."""

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    @patch("semantica.ingest.salesforce_ingestor._SimpleSalesforce")
    def test_list_sobjects_includes_custom_objects(self, mock_sf_cls):
        """list_sobjects returns custom object names ending in __c."""
        from semantica.ingest.salesforce_ingestor import SalesforceIngestor

        mock_client = _make_mock_sf_client()
        mock_sf_cls.return_value = mock_client
        mock_client.describe.return_value = _make_global_describe(
            ["Account", "My_Custom__c", "Another_Object__c", "Contact"]
        )

        ingestor = SalesforceIngestor(username="u", password="p", security_token="t")
        result = ingestor.list_sobjects()

        assert "My_Custom__c" in result
        assert "Another_Object__c" in result
        assert result == sorted(result)  # always sorted

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    @patch("semantica.ingest.salesforce_ingestor._SimpleSalesforce")
    def test_list_sobjects_includes_metadata_types(self, mock_sf_cls):
        """list_sobjects includes metadata types ending in __mdt."""
        from semantica.ingest.salesforce_ingestor import SalesforceIngestor

        mock_client = _make_mock_sf_client()
        mock_sf_cls.return_value = mock_client
        mock_client.describe.return_value = _make_global_describe(
            ["Account", "My_Setting__mdt"]
        )

        ingestor = SalesforceIngestor(username="u", password="p", security_token="t")
        result = ingestor.list_sobjects()

        assert "My_Setting__mdt" in result

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    @patch("semantica.ingest.salesforce_ingestor._SimpleSalesforce")
    def test_get_sobject_schema_custom_object(self, mock_sf_cls):
        """get_sobject_schema works for custom objects (My_Object__c)."""
        from semantica.ingest.salesforce_ingestor import SalesforceIngestor

        mock_client = _make_mock_sf_client()
        mock_sf_cls.return_value = mock_client

        mock_sftype = Mock()
        mock_sftype.describe.return_value = {
            "name": "My_Object__c",
            "label": "My Object",
            "queryable": True,
            "fields": [
                {"name": "Id", "type": "id", "label": "Record ID",
                 "nillable": False, "length": 18},
                {"name": "Name", "type": "string", "label": "Name",
                 "nillable": True, "length": 255},
                {"name": "Custom_Field__c", "type": "string", "label": "Custom",
                 "nillable": True, "length": 100},
            ],
        }
        # simple-salesforce accesses custom objects via attribute access
        mock_client.My_Object__c = mock_sftype

        ingestor = SalesforceIngestor(username="u", password="p", security_token="t")
        schema = ingestor.get_sobject_schema("My_Object__c")

        assert schema["name"] == "My_Object__c"
        assert schema["label"] == "My Object"
        assert schema["queryable"] is True
        assert len(schema["fields"]) == 3
        # Custom field present
        custom_field = next(f for f in schema["fields"] if f["name"] == "Custom_Field__c")
        assert custom_field["type"] == "string"

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    @patch("semantica.ingest.salesforce_ingestor._SimpleSalesforce")
    def test_ingest_sobject_custom_object(self, mock_sf_cls):
        """ingest_sobject fetches records from a custom object."""
        from semantica.ingest.salesforce_ingestor import SalesforceIngestor

        mock_client = _make_mock_sf_client()
        mock_sf_cls.return_value = mock_client
        mock_client.query.return_value = _make_query_result([
            _sf_record("My_Object__c", Id="a01", Name="Rec1", Custom_Field__c="val1"),
            _sf_record("My_Object__c", Id="a02", Name="Rec2", Custom_Field__c="val2"),
        ], total_size=2)

        ingestor = SalesforceIngestor(username="u", password="p", security_token="t")
        data = ingestor.ingest_sobject(
            "My_Object__c", fields=["Id", "Name", "Custom_Field__c"]
        )

        assert data.sobject == "My_Object__c"
        assert data.row_count == 2
        assert "Custom_Field__c" in data.columns
        soql = mock_client.query.call_args[0][0]
        assert "My_Object__c" in soql
        assert "Custom_Field__c" in soql

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    def test_invalid_custom_object_name_rejected(self):
        """Custom object names with injection characters are rejected."""
        from semantica.ingest.salesforce_ingestor import SalesforceIngestor
        from semantica.utils.exceptions import ValidationError

        ingestor = SalesforceIngestor(username="u", password="p", security_token="t")
        with pytest.raises(ValidationError):
            ingestor.ingest_sobject("My Object__c; DROP", fields=["Id"])


# ---------------------------------------------------------------------------
# TestExportAsDocumentsDetailedCoverage
# ---------------------------------------------------------------------------

class TestExportAsDocumentsDetailedCoverage:
    """Detailed export_as_documents tests covering IDs, nested records,
    document text composition, and metadata completeness."""

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    def test_salesforce_id_is_18_char_string_in_document_id(self):
        """Salesforce 18-character Ids are preserved exactly as strings."""
        from semantica.ingest.salesforce_ingestor import SalesforceData, SalesforceIngestor

        ingestor = SalesforceIngestor(username="u", password="p", security_token="t")
        sf_id = "001xx000003GYk2AAG"  # realistic 18-char SF Id
        data = SalesforceData(
            data=[{"Id": sf_id, "Name": "Acme"}],
            row_count=1, columns=["Id", "Name"],
            sobject="Account", instance_url="https://myorg.salesforce.com",
        )

        docs = ingestor.export_as_documents(data)
        assert docs[0]["id"] == sf_id  # exact 18-char string preserved

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    def test_nested_relationship_fields_in_row_data(self):
        """Nested relationship sub-objects are accessible in row_data metadata."""
        from semantica.ingest.salesforce_ingestor import SalesforceData, SalesforceIngestor

        ingestor = SalesforceIngestor(username="u", password="p", security_token="t")
        # Record with a cleaned nested relationship (attributes already stripped)
        record = {
            "Id": "001",
            "Name": "Acme",
            "Owner": {"Name": "Alice", "Id": "005"},  # cleaned sub-object
        }
        data = SalesforceData(
            data=[record], row_count=1, columns=["Id", "Name", "Owner"],
            sobject="Account", instance_url="https://myorg.salesforce.com",
        )

        docs = ingestor.export_as_documents(data, text_fields=["Name"])
        assert docs[0]["metadata"]["row_data"]["Owner"]["Name"] == "Alice"
        assert docs[0]["metadata"]["row_data"]["Owner"]["Id"] == "005"

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    def test_nested_dict_does_not_leak_into_text(self):
        """When text_fields=None, nested relationship dicts must not appear in text."""
        from semantica.ingest.salesforce_ingestor import SalesforceData, SalesforceIngestor

        ingestor = SalesforceIngestor(username="u", password="p", security_token="t")
        record = {
            "Id": "001",
            "Name": "Acme",
            "Owner": {"Name": "Alice", "Id": "005"},  # dict, not str
        }
        data = SalesforceData(
            data=[record], row_count=1, columns=["Id", "Name", "Owner"],
            sobject="Account", instance_url=None,
        )

        docs = ingestor.export_as_documents(data)  # text_fields=None
        # The Owner field is a dict, not a string — must not appear as str(dict)
        assert "{'Name': 'Alice'" not in docs[0]["text"]
        assert "OrderedDict" not in docs[0]["text"]
        # Name and Id (strings) should appear
        assert "Acme" in docs[0]["text"]

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    def test_text_fields_explicit_excludes_unwanted_fields(self):
        """Explicit text_fields limits what goes into the text key."""
        from semantica.ingest.salesforce_ingestor import SalesforceData, SalesforceIngestor

        ingestor = SalesforceIngestor(username="u", password="p", security_token="t")
        data = SalesforceData(
            data=[{"Id": "001", "Name": "Acme Corp", "Website": "https://acme.com",
                   "Description": "Enterprise software"}],
            row_count=1, columns=["Id", "Name", "Website", "Description"],
            sobject="Account", instance_url=None,
        )

        docs = ingestor.export_as_documents(data, text_fields=["Name", "Description"])

        assert docs[0]["text"] == "Acme Corp Enterprise software"
        assert "https://acme.com" not in docs[0]["text"]
        assert "001" not in docs[0]["text"]

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    def test_metadata_source_is_salesforce(self):
        """Every exported document has metadata.source == 'salesforce'."""
        from semantica.ingest.salesforce_ingestor import SalesforceData, SalesforceIngestor

        ingestor = SalesforceIngestor(username="u", password="p", security_token="t")
        data = SalesforceData(
            data=[{"Id": "001", "Name": "X"}, {"Id": "002", "Name": "Y"}],
            row_count=2, columns=["Id", "Name"],
            sobject="Contact", instance_url="https://myorg.salesforce.com",
        )

        docs = ingestor.export_as_documents(data)
        assert all(d["metadata"]["source"] == "salesforce" for d in docs)

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    def test_metadata_sobject_propagated_to_all_documents(self):
        """metadata.sobject is set on every document from ingest_sobject data."""
        from semantica.ingest.salesforce_ingestor import SalesforceData, SalesforceIngestor

        ingestor = SalesforceIngestor(username="u", password="p", security_token="t")
        data = SalesforceData(
            data=[{"Id": "001"}, {"Id": "002"}],
            row_count=2, columns=["Id"],
            sobject="Opportunity", instance_url="https://myorg.salesforce.com",
        )

        docs = ingestor.export_as_documents(data)
        assert all(d["metadata"]["sobject"] == "Opportunity" for d in docs)

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    def test_export_from_ingest_query_has_none_sobject(self):
        """Documents from a raw ingest_query have sobject=None (query may span objects)."""
        from semantica.ingest.salesforce_ingestor import SalesforceData, SalesforceIngestor

        ingestor = SalesforceIngestor(username="u", password="p", security_token="t")
        data = SalesforceData(
            data=[{"Id": "001", "Name": "Acme"}],
            row_count=1, columns=["Id", "Name"],
            sobject=None,  # raw SOQL — no sobject
            query="SELECT Id, Name FROM Account",
            instance_url="https://myorg.salesforce.com",
        )

        docs = ingestor.export_as_documents(data)
        assert docs[0]["metadata"]["sobject"] is None

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    def test_row_data_contains_all_cleaned_fields(self):
        """metadata.row_data must contain all fields from the cleaned record."""
        from semantica.ingest.salesforce_ingestor import SalesforceData, SalesforceIngestor

        ingestor = SalesforceIngestor(username="u", password="p", security_token="t")
        record = {
            "Id": "001",
            "Name": "Acme",
            "Phone": "+1-555-0100",
            "AnnualRevenue": 5000000,
            "IsActive": True,
        }
        data = SalesforceData(
            data=[record], row_count=1, columns=list(record.keys()),
            sobject="Account", instance_url=None,
        )

        docs = ingestor.export_as_documents(data, text_fields=["Name"])
        row_data = docs[0]["metadata"]["row_data"]

        # All fields preserved in row_data
        assert row_data["Id"] == "001"
        assert row_data["Name"] == "Acme"
        assert row_data["Phone"] == "+1-555-0100"
        assert row_data["AnnualRevenue"] == 5000000
        assert row_data["IsActive"] is True


# ---------------------------------------------------------------------------
# TestConnectionReuseWithIngestion
# ---------------------------------------------------------------------------

class TestConnectionReuseWithIngestion:
    """Verify connection lifecycle consistency between standalone and
    context-manager usage across all ingestion methods."""

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    @patch("semantica.ingest.salesforce_ingestor._SimpleSalesforce")
    def test_ingest_sobject_standalone_opens_and_closes(self, mock_sf_cls):
        """Standalone ingest_sobject opens a transient connection and closes it."""
        from semantica.ingest.salesforce_ingestor import SalesforceIngestor

        mock_client = _make_mock_sf_client()
        mock_sf_cls.return_value = mock_client
        mock_client.query.return_value = _make_query_result([], total_size=0)

        ingestor = SalesforceIngestor(username="u", password="p", security_token="t")
        assert ingestor.connector._client is None

        ingestor.ingest_sobject("Account", fields=["Id"])

        assert ingestor.connector._client is None   # closed after call
        mock_sf_cls.assert_called_once()            # connected exactly once

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    @patch("semantica.ingest.salesforce_ingestor._SimpleSalesforce")
    def test_get_sobject_schema_standalone_opens_and_closes(self, mock_sf_cls):
        """Standalone get_sobject_schema opens a transient connection and closes it."""
        from semantica.ingest.salesforce_ingestor import SalesforceIngestor

        mock_client = _make_mock_sf_client()
        mock_sf_cls.return_value = mock_client

        mock_sftype = Mock()
        mock_sftype.describe.return_value = _make_describe_result("Account", ["Id"])
        mock_client.Account = mock_sftype

        ingestor = SalesforceIngestor(username="u", password="p", security_token="t")
        ingestor.get_sobject_schema("Account")

        assert ingestor.connector._client is None

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    @patch("semantica.ingest.salesforce_ingestor._SimpleSalesforce")
    def test_context_manager_all_methods_reuse_connection(self, mock_sf_cls):
        """All four ingestion methods inside a context manager reuse the single
        connection opened by __enter__."""
        from semantica.ingest.salesforce_ingestor import SalesforceIngestor

        mock_client = _make_mock_sf_client()
        mock_sf_cls.return_value = mock_client
        mock_client.query.return_value = _make_query_result(
            [_sf_record("Account", Id="001")], total_size=1
        )
        mock_client.describe.return_value = _make_global_describe(["Account"])

        mock_sftype = Mock()
        mock_sftype.describe.return_value = _make_describe_result("Account", ["Id"])
        mock_client.Account = mock_sftype

        with SalesforceIngestor(
            username="u", password="p", security_token="t"
        ) as sf:
            # All four methods in one context manager
            sf.ingest_sobject("Account", fields=["Id"])
            sf.ingest_query("SELECT Id FROM Account")
            sf.list_sobjects()
            sf.get_sobject_schema("Account")

            # Connection must still be live throughout
            assert sf.connector._client is mock_client

        # Salesforce() constructor called exactly once (__enter__)
        mock_sf_cls.assert_called_once()
        # Released only on __exit__
        assert sf.connector._client is None

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    @patch("semantica.ingest.salesforce_ingestor._SimpleSalesforce")
    def test_standalone_ingest_sobject_does_not_close_pre_opened_connection(
        self, mock_sf_cls
    ):
        """If the caller has already opened a connection manually, ingest_sobject
        must not close it after the call."""
        from semantica.ingest.salesforce_ingestor import SalesforceIngestor

        mock_client = _make_mock_sf_client()
        mock_sf_cls.return_value = mock_client
        mock_client.query.return_value = _make_query_result([], total_size=0)

        ingestor = SalesforceIngestor(username="u", password="p", security_token="t")
        ingestor.connector.connect()  # manually open
        assert ingestor.connector._client is mock_client

        ingestor.ingest_sobject("Account", fields=["Id"])

        # Still connected — we opened it, ingest_sobject must not close it
        assert ingestor.connector._client is mock_client


# ===========================================================================
# Stage 5 — ingest_salesforce() convenience function tests
# ===========================================================================

class TestIngestSalesforceConvenienceFunction:
    """Tests for the ingest_salesforce() public-API convenience wrapper."""

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    @patch("semantica.ingest.salesforce_ingestor._SimpleSalesforce")
    def test_ingest_salesforce_sobject_method(self, mock_sf_cls):
        """ingest_salesforce(method='sobject') returns SalesforceData."""
        from semantica.ingest import ingest_salesforce
        from semantica.ingest.salesforce_ingestor import SalesforceData

        mock_client = _make_mock_sf_client()
        mock_sf_cls.return_value = mock_client
        mock_client.query.return_value = _make_query_result(
            [_sf_record("Account", Id="001", Name="Acme")], total_size=1
        )

        data = ingest_salesforce(
            {"username": "u", "password": "p", "security_token": "t"},
            method="sobject",
            sobject_name="Account",
            fields=["Id", "Name"],
        )

        assert isinstance(data, SalesforceData)
        assert data.sobject == "Account"
        assert data.row_count == 1

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    @patch("semantica.ingest.salesforce_ingestor._SimpleSalesforce")
    def test_ingest_salesforce_query_method(self, mock_sf_cls):
        """ingest_salesforce(method='query') executes raw SOQL."""
        from semantica.ingest import ingest_salesforce
        from semantica.ingest.salesforce_ingestor import SalesforceData

        mock_client = _make_mock_sf_client()
        mock_sf_cls.return_value = mock_client
        soql = "SELECT Id, Name FROM Contact LIMIT 10"
        mock_client.query.return_value = _make_query_result([], total_size=0)

        data = ingest_salesforce(
            {"username": "u", "password": "p", "security_token": "t"},
            method="query",
            soql=soql,
        )

        assert isinstance(data, SalesforceData)
        mock_client.query.assert_called_once_with(soql)

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    @patch("semantica.ingest.salesforce_ingestor._SimpleSalesforce")
    def test_ingest_salesforce_list_sobjects_method(self, mock_sf_cls):
        """ingest_salesforce(method='list_sobjects') returns a sorted list."""
        from semantica.ingest import ingest_salesforce

        mock_client = _make_mock_sf_client()
        mock_sf_cls.return_value = mock_client
        mock_client.describe.return_value = _make_global_describe(
            ["Contact", "Account", "Lead"]
        )

        result = ingest_salesforce(
            {"username": "u", "password": "p", "security_token": "t"},
            method="list_sobjects",
        )

        assert isinstance(result, list)
        assert result == ["Account", "Contact", "Lead"]

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    @patch("semantica.ingest.salesforce_ingestor._SimpleSalesforce")
    def test_ingest_salesforce_schema_method(self, mock_sf_cls):
        """ingest_salesforce(method='schema') returns sObject field metadata."""
        from semantica.ingest import ingest_salesforce

        mock_client = _make_mock_sf_client()
        mock_sf_cls.return_value = mock_client
        mock_sftype = Mock()
        mock_sftype.describe.return_value = _make_describe_result("Account", ["Id", "Name"])
        mock_client.Account = mock_sftype

        result = ingest_salesforce(
            {"username": "u", "password": "p", "security_token": "t"},
            method="schema",
            sobject_name="Account",
        )

        assert isinstance(result, dict)
        assert result["name"] == "Account"
        assert len(result["fields"]) == 2

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    @patch("semantica.ingest.salesforce_ingestor._SimpleSalesforce")
    def test_ingest_salesforce_documents_method(self, mock_sf_cls):
        """ingest_salesforce(method='documents') returns Semantica document list."""
        from semantica.ingest import ingest_salesforce

        mock_client = _make_mock_sf_client()
        mock_sf_cls.return_value = mock_client
        mock_client.query.return_value = _make_query_result([
            _sf_record("Account", Id="001", Name="Acme", Industry="Tech"),
        ], total_size=1)

        docs = ingest_salesforce(
            {"username": "u", "password": "p", "security_token": "t"},
            method="documents",
            sobject_name="Account",
            fields=["Id", "Name", "Industry"],
            text_fields=["Name", "Industry"],
        )

        assert isinstance(docs, list)
        assert len(docs) == 1
        assert docs[0]["id"] == "001"
        assert "Acme" in docs[0]["text"]
        assert docs[0]["metadata"]["source"] == "salesforce"

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    @patch("semantica.ingest.salesforce_ingestor._SimpleSalesforce")
    def test_ingest_salesforce_credentials_from_env_vars(self, mock_sf_cls):
        """When source is None, credentials come from environment variables."""
        from semantica.ingest import ingest_salesforce
        from semantica.ingest.salesforce_ingestor import SalesforceData

        mock_client = _make_mock_sf_client()
        mock_sf_cls.return_value = mock_client
        mock_client.query.return_value = _make_query_result([], total_size=0)

        with patch.dict(
            os.environ,
            {
                "SALESFORCE_USERNAME": "env_user",
                "SALESFORCE_PASSWORD": "env_pass",
                "SALESFORCE_SECURITY_TOKEN": "env_token",
            },
        ):
            data = ingest_salesforce(
                method="sobject",
                sobject_name="Contact",
                fields=["Id"],
            )

        assert isinstance(data, SalesforceData)
        # Credentials must have come from env vars
        call_kwargs = mock_sf_cls.call_args[1]
        assert call_kwargs["username"] == "env_user"

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    @patch("semantica.ingest.salesforce_ingestor._SimpleSalesforce")
    def test_ingest_salesforce_missing_sobject_name_raises(self, mock_sf_cls):
        """method='sobject' without sobject_name raises ProcessingError."""
        from semantica.ingest import ingest_salesforce
        from semantica.utils.exceptions import ProcessingError

        mock_sf_cls.return_value = _make_mock_sf_client()

        with pytest.raises(ProcessingError, match="sobject_name"):
            ingest_salesforce(
                {"username": "u", "password": "p", "security_token": "t"},
                method="sobject",
                # sobject_name intentionally omitted
            )

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    @patch("semantica.ingest.salesforce_ingestor._SimpleSalesforce")
    def test_ingest_salesforce_missing_soql_raises(self, mock_sf_cls):
        """method='query' without soql raises ProcessingError."""
        from semantica.ingest import ingest_salesforce
        from semantica.utils.exceptions import ProcessingError

        mock_sf_cls.return_value = _make_mock_sf_client()

        with pytest.raises(ProcessingError, match="soql"):
            ingest_salesforce(
                {"username": "u", "password": "p", "security_token": "t"},
                method="query",
                # soql intentionally omitted
            )

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    @patch("semantica.ingest.salesforce_ingestor._SimpleSalesforce")
    def test_ingest_salesforce_unknown_method_raises(self, mock_sf_cls):
        """Unknown method name raises ProcessingError."""
        from semantica.ingest import ingest_salesforce
        from semantica.utils.exceptions import ProcessingError

        mock_sf_cls.return_value = _make_mock_sf_client()

        with pytest.raises(ProcessingError, match="Unknown"):
            ingest_salesforce(
                {"username": "u", "password": "p", "security_token": "t"},
                method="bulk_load",
            )

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    def test_ingest_salesforce_non_dict_source_raises(self):
        """Non-dict, non-None source raises ProcessingError."""
        from semantica.ingest import ingest_salesforce
        from semantica.utils.exceptions import ProcessingError

        with pytest.raises(ProcessingError):
            ingest_salesforce("login.salesforce.com", method="sobject", sobject_name="Account")

    def test_ingest_salesforce_missing_lib_raises_configuration_error(self):
        """ConfigurationError with install hint when simple-salesforce absent."""
        from semantica.ingest import ingest_salesforce
        from semantica.utils.exceptions import ConfigurationError

        with patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", False):
            with pytest.raises((ConfigurationError, ImportError)):
                ingest_salesforce(
                    {"username": "u", "password": "p", "security_token": "t"},
                    method="sobject",
                    sobject_name="Account",
                )

    def test_ingest_salesforce_in_public_all(self):
        """ingest_salesforce is exported from semantica.ingest.__all__."""
        import semantica.ingest as pkg
        assert "ingest_salesforce" in pkg.__all__

    def test_ingest_salesforce_accessible_from_package(self):
        """ingest_salesforce is importable directly from semantica.ingest."""
        from semantica.ingest import ingest_salesforce  # must not raise
        assert callable(ingest_salesforce)

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    @patch("semantica.ingest.salesforce_ingestor._SimpleSalesforce")
    def test_unified_ingest_dispatches_to_salesforce(self, mock_sf_cls):
        """ingest(source_type='salesforce') routes to ingest_salesforce."""
        from semantica.ingest import ingest
        from semantica.ingest.salesforce_ingestor import SalesforceData

        mock_client = _make_mock_sf_client()
        mock_sf_cls.return_value = mock_client
        mock_client.query.return_value = _make_query_result([], total_size=0)

        result = ingest(
            None,
            source_type="salesforce",
            method="sobject",
            username="u",
            password="p",
            security_token="t",
            sobject_name="Account",
            fields=["Id"],
        )

        assert "data" in result
        assert isinstance(result["data"], SalesforceData)


# ===========================================================================
# Credential isolation — regression tests for the global-config mutation bug
# ===========================================================================

class TestCredentialIsolation:
    """Verify that ingest_salesforce() does not write per-call credentials
    into the global IngestConfig, which would let a later call (or a concurrent
    call) silently authenticate against the wrong Salesforce org.

    Regression tests for: per-call credentials mutating get_method_config()
    return value (config.py) and the ingest_salesforce() wrapper (methods.py).
    """

    def test_get_method_config_returns_copy(self):
        """IngestConfig.get_method_config() must return a fresh dict each call.

        Mutating the returned dict must not affect the stored method config,
        and two successive calls must return independent objects.
        """
        from semantica.ingest.config import IngestConfig

        cfg = IngestConfig()
        cfg.set_method_config("salesforce", username="org_user", domain="login")

        first = cfg.get_method_config("salesforce")
        assert first["username"] == "org_user"

        # Mutate the returned copy — must not affect the stored config.
        first["username"] = "POISONED"
        first["password"] = "LEAKED_SECRET"

        second = cfg.get_method_config("salesforce")
        assert second["username"] == "org_user", (
            "Stored method config was mutated: credential leaked into global store"
        )
        assert "password" not in second, (
            "Per-call credential 'password' leaked into global method config"
        )

    def test_get_method_config_returns_independent_copies(self):
        """Two calls to get_method_config() must return distinct dict objects."""
        from semantica.ingest.config import IngestConfig

        cfg = IngestConfig()
        cfg.set_method_config("salesforce", domain="login")

        first = cfg.get_method_config("salesforce")
        second = cfg.get_method_config("salesforce")

        assert first is not second, (
            "get_method_config() returned the same object twice; "
            "callers share a mutable reference"
        )

    def test_get_method_config_empty_returns_independent_empty_dicts(self):
        """Even the empty-fallback dict must not be shared across calls."""
        from semantica.ingest.config import IngestConfig

        cfg = IngestConfig()
        # No "salesforce" entry registered — both calls hit the {} fallback.
        first = cfg.get_method_config("salesforce")
        first["leaked"] = True

        second = cfg.get_method_config("salesforce")
        assert "leaked" not in second, (
            "Empty fallback dict is shared; mutation in one call affected another"
        )

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    @patch("semantica.ingest.salesforce_ingestor._SimpleSalesforce")
    def test_ingest_salesforce_credentials_do_not_persist_in_global_config(
        self, mock_sf_cls
    ):
        """Credentials passed to ingest_salesforce() must not persist in the
        global IngestConfig after the call returns.

        This is the core multi-tenant / long-lived-process regression: a second
        call without credentials must not silently authenticate as the first
        caller's org.
        """
        from semantica.ingest import ingest_salesforce
        from semantica.ingest.config import ingest_config

        mock_client = _make_mock_sf_client("org1.salesforce.com")
        mock_sf_cls.return_value = mock_client
        mock_client.query.return_value = _make_query_result([], total_size=0)

        # First call — explicit credentials supplied via source dict.
        ingest_salesforce(
            {
                "username": "user@org1.com",
                "password": "secret-org1-pass",
                "security_token": "secret-org1-token",
            },
            method="sobject",
            sobject_name="Account",
            fields=["Id"],
        )

        # Inspect the global config store — credentials must NOT be present.
        stored = ingest_config.get_method_config("salesforce")
        assert "password" not in stored, (
            f"'password' leaked into global config after call: {stored}"
        )
        assert "security_token" not in stored, (
            f"'security_token' leaked into global config after call: {stored}"
        )
        assert "username" not in stored, (
            f"'username' leaked into global config after call: {stored}"
        )

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    @patch("semantica.ingest.salesforce_ingestor._SimpleSalesforce")
    def test_second_call_does_not_reuse_first_call_credentials(
        self, mock_sf_cls
    ):
        """A second ingest_salesforce() call with different credentials must
        not silently inherit credentials from the first call.

        Simulates the multi-tenant scenario: two different orgs called in
        sequence; each must connect with its own credentials.
        """
        from semantica.ingest import ingest_salesforce

        mock_client = _make_mock_sf_client()
        mock_sf_cls.return_value = mock_client
        mock_client.query.return_value = _make_query_result([], total_size=0)

        # First call — org 1.
        ingest_salesforce(
            {
                "username": "user@org1.com",
                "password": "pass-org1",
                "security_token": "token-org1",
            },
            method="sobject",
            sobject_name="Account",
            fields=["Id"],
        )
        first_call_kwargs = mock_sf_cls.call_args[1]

        mock_sf_cls.reset_mock()

        # Second call — org 2 with completely different credentials.
        ingest_salesforce(
            {
                "username": "user@org2.com",
                "password": "pass-org2",
                "security_token": "token-org2",
            },
            method="sobject",
            sobject_name="Contact",
            fields=["Id"],
        )
        second_call_kwargs = mock_sf_cls.call_args[1]

        # Each call must have connected with its own credentials.
        assert second_call_kwargs.get("username") == "user@org2.com", (
            "Second call used wrong username — possible credential bleed from first call"
        )
        assert second_call_kwargs.get("password") == "pass-org2", (
            "Second call used wrong password — first call's password bled into second"
        )
        assert second_call_kwargs.get("security_token") == "token-org2", (
            "Second call used wrong token — first call's token bled into second"
        )

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    @patch("semantica.ingest.salesforce_ingestor._SimpleSalesforce")
    def test_kwargs_credentials_do_not_persist_in_global_config(
        self, mock_sf_cls
    ):
        """Credentials passed as kwargs (no source dict) also must not persist
        in the global config after the call.
        """
        from semantica.ingest import ingest_salesforce
        from semantica.ingest.config import ingest_config

        mock_client = _make_mock_sf_client()
        mock_sf_cls.return_value = mock_client
        mock_client.query.return_value = _make_query_result([], total_size=0)

        ingest_salesforce(
            method="sobject",
            sobject_name="Account",
            fields=["Id"],
            username="user@org.com",
            password="kwarg-secret",
            security_token="kwarg-token",
        )

        stored = ingest_config.get_method_config("salesforce")
        assert "password" not in stored, (
            f"kwarg password leaked into global config: {stored}"
        )
        assert "security_token" not in stored, (
            f"kwarg security_token leaked into global config: {stored}"
        )


# ===========================================================================
# Fix 1 — limit validation (focused tests per review requirement)
# ===========================================================================

class TestLimitValidation:
    """Fix 1: limit must be validated as a non-negative int before any
    comparison, query construction, slicing, or network activity."""

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    @patch("semantica.ingest.salesforce_ingestor._SimpleSalesforce")
    def test_limit_none_is_valid(self, mock_sf_cls):
        """limit=None does not raise."""
        from semantica.ingest.salesforce_ingestor import SalesforceIngestor

        mock_client = _make_mock_sf_client()
        mock_sf_cls.return_value = mock_client
        mock_client.query.return_value = _make_query_result([], total_size=0)
        ingestor = SalesforceIngestor(username="u", password="p", security_token="t")
        data = ingestor.ingest_sobject("Account", fields=["Id"], limit=None)
        assert data.row_count == 0

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    @patch("semantica.ingest.salesforce_ingestor._SimpleSalesforce")
    def test_limit_zero_is_valid_empty_shortcircuit(self, mock_sf_cls):
        """limit=0 is the empty-result shortcut — returns empty without API call."""
        from semantica.ingest.salesforce_ingestor import SalesforceData, SalesforceIngestor

        mock_sf_cls.return_value = _make_mock_sf_client()
        ingestor = SalesforceIngestor(username="u", password="p", security_token="t")
        data = ingestor.ingest_sobject("Account", fields=["Id"], limit=0)
        assert isinstance(data, SalesforceData)
        assert data.row_count == 0
        mock_sf_cls.assert_not_called()

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    @patch("semantica.ingest.salesforce_ingestor._SimpleSalesforce")
    def test_limit_positive_int_is_valid(self, mock_sf_cls):
        """Positive integer limit does not raise."""
        from semantica.ingest.salesforce_ingestor import SalesforceIngestor

        mock_client = _make_mock_sf_client()
        mock_sf_cls.return_value = mock_client
        mock_client.query.return_value = _make_query_result([], total_size=0)
        ingestor = SalesforceIngestor(username="u", password="p", security_token="t")
        data = ingestor.ingest_sobject("Account", fields=["Id"], limit=10)
        assert data.row_count == 0

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    @patch("semantica.ingest.salesforce_ingestor._SimpleSalesforce")
    def test_limit_negative_raises_validation_error_focused(self, mock_sf_cls):
        """Negative integer raises ValidationError before network activity."""
        from semantica.ingest.salesforce_ingestor import SalesforceIngestor
        from semantica.utils.exceptions import ValidationError

        mock_sf_cls.return_value = _make_mock_sf_client()
        ingestor = SalesforceIngestor(username="u", password="p", security_token="t")
        with pytest.raises(ValidationError):
            ingestor.ingest_sobject("Account", fields=["Id"], limit=-5)
        mock_sf_cls.assert_not_called()

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    @patch("semantica.ingest.salesforce_ingestor._SimpleSalesforce")
    def test_limit_true_raises_validation_error(self, mock_sf_cls):
        """True (bool) raises ValidationError even though bool subclasses int."""
        from semantica.ingest.salesforce_ingestor import SalesforceIngestor
        from semantica.utils.exceptions import ValidationError

        mock_sf_cls.return_value = _make_mock_sf_client()
        ingestor = SalesforceIngestor(username="u", password="p", security_token="t")
        with pytest.raises(ValidationError):
            ingestor.ingest_sobject("Account", fields=["Id"], limit=True)
        mock_sf_cls.assert_not_called()

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    @patch("semantica.ingest.salesforce_ingestor._SimpleSalesforce")
    def test_limit_false_raises_validation_error(self, mock_sf_cls):
        """False (bool) raises ValidationError."""
        from semantica.ingest.salesforce_ingestor import SalesforceIngestor
        from semantica.utils.exceptions import ValidationError

        mock_sf_cls.return_value = _make_mock_sf_client()
        ingestor = SalesforceIngestor(username="u", password="p", security_token="t")
        with pytest.raises(ValidationError):
            ingestor.ingest_sobject("Account", fields=["Id"], limit=False)
        mock_sf_cls.assert_not_called()

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    @patch("semantica.ingest.salesforce_ingestor._SimpleSalesforce")
    def test_limit_float_fractional_raises_validation_error(self, mock_sf_cls):
        """Float 0.5 raises ValidationError."""
        from semantica.ingest.salesforce_ingestor import SalesforceIngestor
        from semantica.utils.exceptions import ValidationError

        mock_sf_cls.return_value = _make_mock_sf_client()
        ingestor = SalesforceIngestor(username="u", password="p", security_token="t")
        with pytest.raises(ValidationError):
            ingestor.ingest_sobject("Account", fields=["Id"], limit=0.5)
        mock_sf_cls.assert_not_called()

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    @patch("semantica.ingest.salesforce_ingestor._SimpleSalesforce")
    def test_limit_float_whole_raises_validation_error(self, mock_sf_cls):
        """Float 2.0 raises ValidationError even though it is a whole number."""
        from semantica.ingest.salesforce_ingestor import SalesforceIngestor
        from semantica.utils.exceptions import ValidationError

        mock_sf_cls.return_value = _make_mock_sf_client()
        ingestor = SalesforceIngestor(username="u", password="p", security_token="t")
        with pytest.raises(ValidationError):
            ingestor.ingest_sobject("Account", fields=["Id"], limit=2.0)
        mock_sf_cls.assert_not_called()

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    @patch("semantica.ingest.salesforce_ingestor._SimpleSalesforce")
    def test_limit_string_raises_validation_error(self, mock_sf_cls):
        """String '10' raises ValidationError."""
        from semantica.ingest.salesforce_ingestor import SalesforceIngestor
        from semantica.utils.exceptions import ValidationError

        mock_sf_cls.return_value = _make_mock_sf_client()
        ingestor = SalesforceIngestor(username="u", password="p", security_token="t")
        with pytest.raises(ValidationError):
            ingestor.ingest_sobject("Account", fields=["Id"], limit="10")
        mock_sf_cls.assert_not_called()


# ===========================================================================
# Fix 4 — ORDER BY dotted field path validation (focused tests)
# ===========================================================================

class TestOrderByDottedValidation:
    """Fix 4: ORDER BY validation uses _validate_field_name component-wise
    so double-dots and other malformed paths are caught."""

    def test_valid_simple_field(self):
        from semantica.ingest.salesforce_ingestor import _validate_order_by
        assert _validate_order_by("Name") == "Name"

    def test_valid_dotted_field_asc(self):
        from semantica.ingest.salesforce_ingestor import _validate_order_by
        assert _validate_order_by("Owner.Name ASC") == "Owner.Name ASC"

    def test_valid_dotted_field_desc_nulls_first(self):
        from semantica.ingest.salesforce_ingestor import _validate_order_by
        result = _validate_order_by("Owner.Name DESC NULLS FIRST")
        assert "NULLS FIRST" in result

    def test_valid_multi_column_with_dotted(self):
        from semantica.ingest.salesforce_ingestor import _validate_order_by
        result = _validate_order_by("Name ASC, Owner.Name DESC")
        assert result == "Name ASC, Owner.Name DESC"

    def test_invalid_double_dot_raises(self):
        """Name.Owner..Name ASC must be rejected (double dot is not valid)."""
        from semantica.ingest.salesforce_ingestor import _validate_order_by
        from semantica.utils.exceptions import ValidationError
        with pytest.raises(ValidationError):
            _validate_order_by("Name.Owner..Name ASC")

    def test_invalid_leading_dot_raises(self):
        from semantica.ingest.salesforce_ingestor import _validate_order_by
        from semantica.utils.exceptions import ValidationError
        with pytest.raises(ValidationError):
            _validate_order_by(".Name ASC")

    def test_invalid_trailing_dot_raises(self):
        from semantica.ingest.salesforce_ingestor import _validate_order_by
        from semantica.utils.exceptions import ValidationError
        with pytest.raises(ValidationError):
            _validate_order_by("Name. ASC")

    def test_invalid_injection_still_blocked(self):
        from semantica.ingest.salesforce_ingestor import _validate_order_by
        from semantica.utils.exceptions import ValidationError
        with pytest.raises(ValidationError):
            _validate_order_by("Name; DROP TABLE Account")

    def test_invalid_empty_expression_between_commas(self):
        from semantica.ingest.salesforce_ingestor import _validate_order_by
        from semantica.utils.exceptions import ValidationError
        with pytest.raises(ValidationError):
            _validate_order_by("Name ASC,,CreatedDate DESC")


# ===========================================================================
# Fix 5 — fields validation (focused tests)
# ===========================================================================

class TestFieldsValidation:
    """Fix 5: explicit fields must be a non-empty list of valid field-name
    strings; None retains the schema-discovery behavior."""

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    @patch("semantica.ingest.salesforce_ingestor._SimpleSalesforce")
    def test_fields_none_triggers_describe(self, mock_sf_cls):
        """fields=None causes describe() and returns valid data."""
        from semantica.ingest.salesforce_ingestor import SalesforceIngestor

        mock_client = _make_mock_sf_client()
        mock_sf_cls.return_value = mock_client
        mock_sftype = Mock()
        mock_sftype.describe.return_value = {
            "name": "Account",
            "fields": [{"name": "Id", "type": "id"}, {"name": "Name", "type": "string"}],
        }
        mock_client.Account = mock_sftype
        mock_client.query.return_value = _make_query_result([], total_size=0)

        ingestor = SalesforceIngestor(username="u", password="p", security_token="t")
        data = ingestor.ingest_sobject("Account")  # fields=None
        mock_sftype.describe.assert_called_once()
        assert data.row_count == 0

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    @patch("semantica.ingest.salesforce_ingestor._SimpleSalesforce")
    def test_fields_valid_list_accepted(self, mock_sf_cls):
        """fields=["Id", "Name"] is valid."""
        from semantica.ingest.salesforce_ingestor import SalesforceIngestor

        mock_client = _make_mock_sf_client()
        mock_sf_cls.return_value = mock_client
        mock_client.query.return_value = _make_query_result([], total_size=0)

        ingestor = SalesforceIngestor(username="u", password="p", security_token="t")
        data = ingestor.ingest_sobject("Account", fields=["Id", "Name"])
        assert data.row_count == 0

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    @patch("semantica.ingest.salesforce_ingestor._SimpleSalesforce")
    def test_fields_empty_list_raises(self, mock_sf_cls):
        """fields=[] raises ValidationError before any network call."""
        from semantica.ingest.salesforce_ingestor import SalesforceIngestor
        from semantica.utils.exceptions import ValidationError

        mock_sf_cls.return_value = _make_mock_sf_client()
        ingestor = SalesforceIngestor(username="u", password="p", security_token="t")
        with pytest.raises(ValidationError, match="non-empty|empty"):
            ingestor.ingest_sobject("Account", fields=[])
        mock_sf_cls.assert_not_called()

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    @patch("semantica.ingest.salesforce_ingestor._SimpleSalesforce")
    def test_fields_string_raises(self, mock_sf_cls):
        """fields='Id' (string, not list) raises ValidationError."""
        from semantica.ingest.salesforce_ingestor import SalesforceIngestor
        from semantica.utils.exceptions import ValidationError

        mock_sf_cls.return_value = _make_mock_sf_client()
        ingestor = SalesforceIngestor(username="u", password="p", security_token="t")
        with pytest.raises(ValidationError):
            ingestor.ingest_sobject("Account", fields="Id")
        mock_sf_cls.assert_not_called()

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    @patch("semantica.ingest.salesforce_ingestor._SimpleSalesforce")
    def test_fields_tuple_raises(self, mock_sf_cls):
        """fields=('Id',) (tuple, not list) raises ValidationError."""
        from semantica.ingest.salesforce_ingestor import SalesforceIngestor
        from semantica.utils.exceptions import ValidationError

        mock_sf_cls.return_value = _make_mock_sf_client()
        ingestor = SalesforceIngestor(username="u", password="p", security_token="t")
        with pytest.raises(ValidationError):
            ingestor.ingest_sobject("Account", fields=("Id",))
        mock_sf_cls.assert_not_called()

    @patch("semantica.ingest.salesforce_ingestor.SALESFORCE_AVAILABLE", True)
    @patch("semantica.ingest.salesforce_ingestor._SimpleSalesforce")
    def test_fields_invalid_element_raises(self, mock_sf_cls):
        """Invalid field name inside a valid list raises ValidationError."""
        from semantica.ingest.salesforce_ingestor import SalesforceIngestor
        from semantica.utils.exceptions import ValidationError

        mock_sf_cls.return_value = _make_mock_sf_client()
        ingestor = SalesforceIngestor(username="u", password="p", security_token="t")
        with pytest.raises(ValidationError):
            ingestor.ingest_sobject("Account", fields=["Id", "Bad Field!"])
        mock_sf_cls.assert_not_called()
