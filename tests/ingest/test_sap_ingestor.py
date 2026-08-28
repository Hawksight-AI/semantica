"""Tests for the SAP OData ingestor.

The SAP connector never touches a live SAP system: every outbound request goes
through ``semantica.ingest.ssrf.request_with_ssrf_guard`` (see
``sap_ingestor.py``), so these tests patch that single entry point and drive
the parser / connector / ingestor with canned responses.

Covered:
- ``$metadata`` (CSDL XML) -> entity set discovery & property fields
- OData v2 atom (``__next``) and OData v4 (``@odata.nextLink``) pagination
- Basic and OAuth2 credential payloads propagated on the request
- SSRF guard is used for data *and* token-exchange requests
- ``export_as_documents`` yields the flat document shape GraphBuilder expects
"""

from unittest.mock import MagicMock, patch

import pytest
import requests

from semantica.ingest import SAPIngestor, SAPODataConnector, SAPODataEntity
from semantica.utils.exceptions import ProcessingError, ValidationError

METADATA_V2 = """<?xml version="1.0" encoding="utf-8"?>
<edmx:Edmx Version="1.0" xmlns:edmx="http://schemas.microsoft.com/ado/2007/06/edmx">
  <edmx:DataServices
      xmlns:m="http://schemas.microsoft.com/ado/2007/08/dataservices/metadata">
    <Schema Namespace="SAPService" xmlns="http://schemas.microsoft.com/ado/2008/09/edm">
      <EntityContainer Name="Default" m:IsDefaultEntityContainer="true">
        <EntitySet Name="SalesOrderSet" EntityType="SAPService.SalesOrder"/>
        <EntitySet Name="CustomerSet" EntityType="SAPService.Customer"/>
      </EntityContainer>
      <EntityType Name="SalesOrder">
        <Key><PropertyRef Name="SalesOrderID"/></Key>
        <Property Name="SalesOrderID" Type="Edm.String" Nullable="false"/>
        <Property Name="CustomerID" Type="Edm.String"/>
        <Property Name="GrossAmount" Type="Edm.Decimal"/>
      </EntityType>
      <EntityType Name="Customer">
        <Key><PropertyRef Name="CustomerID"/></Key>
        <Property Name="CustomerID" Type="Edm.String" Nullable="false"/>
        <Property Name="Name" Type="Edm.String"/>
      </EntityType>
    </Schema>
  </edmx:DataServices>
</edmx:Edmx>
"""

METADATA_V4 = """<?xml version="1.0" encoding="utf-8"?>
<edmx:Edmx Version="4.0" xmlns:edmx="http://docs.oasis-open.org/odata/ns/edmx">
  <edmx:DataServices>
    <Schema Namespace="SalesNs" xmlns="http://docs.oasis-open.org/odata/ns/edm">
      <EntityContainer Name="Svc">
        <EntitySet Name="SalesOrders" EntityType="SalesNs.SalesOrder"/>
        <EntitySet Name="Customers" EntityType="SalesNs.Customer"/>
      </EntityContainer>
      <EntityType Name="SalesOrder">
        <Property Name="ID" Type="Edm.String"/>
        <Property Name="Total" Type="Edm.Decimal" Nullable="false"/>
      </EntityType>
      <EntityType Name="Customer">
        <Property Name="ID" Type="Edm.String"/>
        <Property Name="Name" Type="Edm.String"/>
      </EntityType>
    </Schema>
  </edmx:DataServices>
</edmx:Edmx>
"""

METADATA_MULTI_SCHEMA = """<?xml version="1.0" encoding="utf-8"?>
<edmx:Edmx Version="1.0" xmlns:edmx="http://schemas.microsoft.com/ado/2007/06/edmx">
  <edmx:DataServices>
    <Schema Namespace="OrdersNs" xmlns="http://schemas.microsoft.com/ado/2008/09/edm">
      <EntityContainer Name="OrdersSvc">
        <EntitySet Name="OrdersNs" EntityType="OrdersNs.Row"/>
      </EntityContainer>
      <EntityType Name="Row">
        <Property Name="A" Type="Edm.String"/>
      </EntityType>
    </Schema>
    <Schema Namespace="InvoicesNs" xmlns="http://schemas.microsoft.com/ado/2008/09/edm">
      <EntityContainer Name="InvoicesSvc">
        <EntitySet Name="InvoicesNs" EntityType="InvoicesNs.Row"/>
      </EntityContainer>
      <EntityType Name="Row">
        <Property Name="B" Type="Edm.String"/>
      </EntityType>
    </Schema>
  </edmx:DataServices>
</edmx:Edmx>
"""


def _fake_response(status_code=200, json_payload=None, text="", headers=None):
    """requests.Response-like stand-in returned by the mocked guard."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.headers = headers or {}
    resp.text = text
    resp.url = "https://sap.example/odata/$metadata"
    if json_payload is not None:
        resp.json.return_value = json_payload
    else:
        resp.json.side_effect = ValueError("not json")
    if status_code >= 400:
        resp.raise_for_status.side_effect = requests.exceptions.HTTPError(
            f"{status_code} error"
        )
    return resp


def _json_resp(payload, url):
    r = MagicMock()
    r.status_code = 200
    r.headers = {"content-type": "application/json"}
    r.text = ""
    r.url = url
    r.json.return_value = payload
    return r


class TestDiscoverService:
    def test_metadata_parses_entity_sets_and_fields(self):
        resp = MagicMock()
        resp.status_code = 200
        resp.headers = {"content-type": "application/xml"}
        resp.text = METADATA_V2
        resp.json.side_effect = ValueError("xml not json")

        with patch(
            "semantica.ingest.sap_ingestor.request_with_ssrf_guard",
            return_value=resp,
        ) as guard:
            ing = SAPIngestor(
                base_url="https://sap.example/odata/", username="u", password="p"
            )
            sets = ing.discover_service()

        assert guard.call_count == 1
        assert [s["name"] for s in sets] == ["SalesOrderSet", "CustomerSet"]
        sales = next(s for s in sets if s["name"] == "SalesOrderSet")
        assert {f["name"] for f in sales["fields"]} == {
            "SalesOrderID",
            "CustomerID",
            "GrossAmount",
        }
        assert sales["fields"][0]["type"] == "Edm.String"

    def test_discover_flow_routes_via_ssrf(self):
        resp = MagicMock()
        resp.status_code = 200
        resp.headers = {}
        resp.text = METADATA_V2
        resp.json.side_effect = ValueError()

        with patch("semantica.ingest.sap_ingestor.request_with_ssrf_guard") as guard:
            guard.return_value = resp
            ing = SAPIngestor(
                base_url="https://sap.example/odata/", username="u", password="p"
            )
            ing.discover_service()

        method, url = guard.call_args[0]
        assert method == "GET"
        assert url.endswith("$metadata")

    def test_metadata_url_keeps_last_segment_without_trailing_slash(self):
        """base_url without a trailing '/' must not lose its last segment.

        urljoin() replaces the final path segment when the base has no
        trailing slash, which would silently turn .../API_BUSINESS_PARTNER
        into .../$metadata against the wrong service root.
        """
        resp = MagicMock()
        resp.status_code = 200
        resp.headers = {}
        resp.text = METADATA_V2
        resp.json.side_effect = ValueError()

        with patch(
            "semantica.ingest.sap_ingestor.request_with_ssrf_guard",
            return_value=resp,
        ) as guard:
            ing = SAPIngestor(
                base_url="https://sap.example/odata/API_BUSINESS_PARTNER",
                username="u",
                password="p",
            )
            ing.discover_service()

        method, url = guard.call_args[0]
        assert url == "https://sap.example/odata/API_BUSINESS_PARTNER/$metadata"

    def test_service_root_appends_metadata(self):
        """service is a service root (same meaning as ingest_entity_set):
        $metadata is appended automatically, not treated as the full path.
        """
        resp = MagicMock()
        resp.status_code = 200
        resp.headers = {}
        resp.text = METADATA_V2
        resp.json.side_effect = ValueError()

        with patch(
            "semantica.ingest.sap_ingestor.request_with_ssrf_guard",
            return_value=resp,
        ) as guard:
            ing = SAPIngestor(
                base_url="https://sap.example/odata/sap/",
                username="u",
                password="p",
            )
            ing.discover_service("API_BUSINESS_PARTNER")

        _, url = guard.call_args[0]
        assert url == "https://sap.example/odata/sap/API_BUSINESS_PARTNER/$metadata"

    def test_absolute_service_root_appends_metadata(self):
        resp = MagicMock()
        resp.status_code = 200
        resp.headers = {}
        resp.text = METADATA_V2
        resp.json.side_effect = ValueError()

        with patch(
            "semantica.ingest.sap_ingestor.request_with_ssrf_guard",
            return_value=resp,
        ) as guard:
            ing = SAPIngestor(
                base_url="https://sap.example/odata/sap/",
                username="u",
                password="p",
            )
            ing.discover_service("https://other.example/services/sap/")

        _, url = guard.call_args[0]
        assert url == "https://other.example/services/sap/$metadata"

    def test_v4_oasis_metadata_parses_with_nullable_defaults(self):
        resp = _fake_response(
            text=METADATA_V4, headers={"content-type": "application/xml"}
        )
        with patch(
            "semantica.ingest.sap_ingestor.request_with_ssrf_guard",
            return_value=resp,
        ):
            ing = SAPIngestor(
                base_url="https://sap.example/odata/",
                username="u",
                password="p",
            )
            sets = ing.discover_service()

        by_name = {s["name"]: s for s in sets}
        assert "SalesOrders" in by_name and "Customers" in by_name
        sales_fields = {f["name"]: f for f in by_name["SalesOrders"]["fields"]}
        # Omitted Nullable -> nullable (CSDL default); explicit "false" honored.
        assert sales_fields["ID"]["nullable"] is True
        assert sales_fields["Total"]["nullable"] is False

    def test_same_named_types_in_different_schemas_do_not_merge(self):
        resp = _fake_response(
            text=METADATA_MULTI_SCHEMA, headers={"content-type": "application/xml"}
        )
        with patch(
            "semantica.ingest.sap_ingestor.request_with_ssrf_guard",
            return_value=resp,
        ):
            ing = SAPIngestor(
                base_url="https://sap.example/odata/",
                username="u",
                password="p",
            )
            sets = ing.discover_service()

        by_name = {s["name"]: s for s in sets}
        assert [f["name"] for f in by_name["OrdersNs"]["fields"]] == ["A"]
        assert [f["name"] for f in by_name["InvoicesNs"]["fields"]] == ["B"]


class TestAuth:
    def test_basic_auth_payload_attached(self):
        conn = SAPODataConnector(
            base_url="https://sap.example/odata/",
            username="erp_user",
            # Non-functional test placeholder; the low-entropy value keeps the
            # secret scanner from treating it as a hardcoded credential.
            password="test",
        )
        session = conn.get_session()
        assert session.headers["Authorization"].startswith("Basic ")
        # base64("erp_user:test")
        assert session.headers["Authorization"].endswith("ZXJwX3VzZXI6dGVzdA==")

    def test_oauth_token_exchange_goes_through_ssrf(self):
        token_resp = MagicMock()
        token_resp.status_code = 200
        token_resp.headers = {}
        token_resp.json.return_value = {"access_token": "tok-123"}

        with patch(
            "semantica.ingest.sap_ingestor.request_with_ssrf_guard",
            return_value=token_resp,
        ) as guard:
            conn = SAPODataConnector(
                base_url="https://sap.example/odata/",
                token_url="https://auth.example/oauth/token",
                client_id="cid",
                client_secret="secret",
            )
            session = conn.get_session()

        assert guard.call_count == 1
        method_tok, url = guard.call_args[0]
        assert method_tok == "POST"
        assert url == "https://auth.example/oauth/token"
        assert session.headers["Authorization"] == "Bearer tok-123"
        body = guard.call_args.kwargs.get("data", {})
        assert body["grant_type"] == "client_credentials"

    def test_requires_auth(self):
        with pytest.raises(ValidationError):
            SAPODataConnector(base_url="https://sap.example/odata/")

    def test_requires_base_url(self):
        with pytest.raises(ValidationError):
            SAPODataConnector(username="u", password="p")


class TestIngestPagination:
    V4_PAGE = {
        "value": [{"SalesOrderID": "SO-1"}, {"SalesOrderID": "SO-2"}],
        "@odata.nextLink": "https://sap.example/odata/SalesOrderSet?$skiptoken=abc",
    }
    V4_LAST = {"value": [{"SalesOrderID": "SO-3"}]}

    def test_v4_nextlink_paginates(self):
        calls = []

        def fake_guard(method, url, **kw):
            page1 = _json_resp(self.V4_PAGE, url)
            page2 = _json_resp(self.V4_LAST, url)
            calls.append(url)
            return page1 if method == "GET" and len(calls) == 1 else page2

        with patch(
            "semantica.ingest.sap_ingestor.request_with_ssrf_guard",
            side_effect=fake_guard,
        ):
            ing = SAPIngestor(
                base_url="https://sap.example/odata/",
                username="u",
                password="p",
            )
            result = ing.ingest_entity_set(entity_set="SalesOrderSet")

        assert result.count == 3
        assert [r["SalesOrderID"] for r in result.records] == [
            "SO-1",
            "SO-2",
            "SO-3",
        ]
        # Reached the second page's next link then stopped.
        assert len(calls) == 2

    def test_v4_nextlink_is_followed_past_first_page(self):
        calls = []

        def fake_guard(method, url, **kw):
            calls.append(url)
            if len(calls) == 1:
                return _json_resp(self.V4_PAGE, url)
            return _json_resp(self.V4_LAST, url)

        with patch(
            "semantica.ingest.sap_ingestor.request_with_ssrf_guard",
            side_effect=fake_guard,
        ):
            ing = SAPIngestor(
                base_url="https://sap.example/odata/",
                username="u",
                password="p",
            )
            ing.ingest_entity_set(entity_set="SalesOrderSet")
        assert len(calls) == 2

    def test_v2_atom_next_pagination(self):
        v2_first = {
            "d": {
                "results": [{"SalesOrderID": "A"}],
                "__next": {"__deferred": {"uri": "https://sap.example/odata/next2"}},
            },
        }
        v2_last = {"d": {"results": [{"SalesOrderID": "B"}]}}
        calls = []

        def fake_guard(method, url, **kw):
            calls.append(url)
            return (
                _json_resp(v2_first, url)
                if len(calls) == 1
                else _json_resp(v2_last, url)
            )

        with patch(
            "semantica.ingest.sap_ingestor.request_with_ssrf_guard",
            side_effect=fake_guard,
        ):
            ing = SAPIngestor(
                base_url="https://sap.example/odata/",
                username="u",
                password="p",
            )
            result = ing.ingest_entity_set(entity_set="SalesOrderSet")

        assert [r["SalesOrderID"] for r in result.records] == ["A", "B"]
        assert len(calls) == 2

    def test_v2_next_as_plain_string_paginates(self):
        """Canonical OData v2 JSON: ``__next`` is a plain string URL."""
        v2_first = {
            "d": {
                "results": [{"SalesOrderID": "A"}],
                "__next": "https://sap.example/odata/next2",
            },
        }
        v2_last = {"d": {"results": [{"SalesOrderID": "B"}]}}
        calls = []

        def fake_guard(method, url, **kw):
            calls.append(url)
            if len(calls) == 1:
                return _json_resp(v2_first, url)
            return _json_resp(v2_last, url)

        with patch(
            "semantica.ingest.sap_ingestor.request_with_ssrf_guard",
            side_effect=fake_guard,
        ):
            ing = SAPIngestor(
                base_url="https://sap.example/odata/",
                username="u",
                password="p",
            )
            result = ing.ingest_entity_set(entity_set="SalesOrderSet")

        assert [r["SalesOrderID"] for r in result.records] == ["A", "B"]
        assert len(calls) == 2

    def test_relative_service_resolves_against_base(self):
        with patch(
            "semantica.ingest.sap_ingestor.request_with_ssrf_guard",
            return_value=_json_resp({"value": []}, "https://x/"),
        ) as guard:
            ing = SAPIngestor(
                base_url="https://sap.example/odata/sap/",
                username="u",
                password="p",
            )
            ing.ingest_entity_set(
                service="API_SALES_ORDER_SRV", entity_set="SalesOrderSet"
            )

        method, url = guard.call_args[0]
        assert url == "https://sap.example/odata/sap/API_SALES_ORDER_SRV/SalesOrderSet"

    def test_expand_passthrough_for_line_items(self):
        with patch(
            "semantica.ingest.sap_ingestor.request_with_ssrf_guard",
            return_value=_json_resp(
                {"value": [{"SalesOrderID": "SO-9"}]}, "https://x/"
            ),
        ) as guard:
            ing = SAPIngestor(
                base_url="https://sap.example/odata/", username="u", password="p"
            )
            ing.ingest_entity_set(entity_set="SalesOrderSet", expand="to_Item")

        params = guard.call_args_list[0].kwargs.get("params") or {}
        assert params.get("$expand") == "to_Item"

    def test_select_filter_top_skip_objects_passthrough(self):
        with patch(
            "semantica.ingest.sap_ingestor.request_with_ssrf_guard",
            return_value=_json_resp({"value": []}, "https://x/"),
        ) as guard:
            ing = SAPIngestor(
                base_url="https://sap.example/odata/", username="u", password="p"
            )
            ing.ingest_entity_set(
                entity_set="SalesOrderSet",
                select="SalesOrderID,GrossAmount",
                filter="GrossAmount gt 100",
                top=5,
                skip=2,
            )
        params = guard.call_args_list[0].kwargs.get("params") or {}
        assert params["$select"] == "SalesOrderID,GrossAmount"
        assert params["$filter"] == "GrossAmount gt 100"
        assert params["$top"] == "5"
        assert params["$skip"] == "2"


class TestErrorPaths:
    def test_http_error_on_entity_set_raises_processing_error(self):
        with patch(
            "semantica.ingest.sap_ingestor.request_with_ssrf_guard",
            return_value=_fake_response(status_code=403),
        ):
            ing = SAPIngestor(
                base_url="https://sap.example/odata/",
                username="u",
                password="p",
            )
            with pytest.raises(ProcessingError, match="403"):
                ing.ingest_entity_set(entity_set="SalesOrderSet")

    def test_invalid_metadata_xml_raises_processing_error(self):
        resp = _fake_response(text="<not-xml")
        with patch(
            "semantica.ingest.sap_ingestor.request_with_ssrf_guard",
            return_value=resp,
        ):
            ing = SAPIngestor(
                base_url="https://sap.example/odata/",
                username="u",
                password="p",
            )
            with pytest.raises(ProcessingError, match="not valid XML"):
                ing.discover_service()

    def test_non_json_entity_response_raises_processing_error(self):
        resp = _fake_response(text="plain text")
        with patch(
            "semantica.ingest.sap_ingestor.request_with_ssrf_guard",
            return_value=resp,
        ):
            ing = SAPIngestor(
                base_url="https://sap.example/odata/",
                username="u",
                password="p",
            )
            with pytest.raises(ProcessingError, match="not JSON"):
                ing.ingest_entity_set(entity_set="SalesOrderSet")

    def test_cross_host_next_link_rejected(self):
        first = _json_resp(
            {
                "value": [{"SalesOrderID": "A"}],
                "@odata.nextLink": "https://evil.example/next",
            },
            "https://sap.example/odata/SalesOrderSet",
        )

        with patch(
            "semantica.ingest.sap_ingestor.request_with_ssrf_guard",
            return_value=first,
        ) as guard:
            ing = SAPIngestor(
                base_url="https://sap.example/odata/",
                username="u",
                password="p",
            )
            with pytest.raises(ProcessingError, match="different host"):
                ing.ingest_entity_set(entity_set="SalesOrderSet")
        # The credential-bearing session is never sent to the evil host.
        assert guard.call_count == 1

    def test_top_zero_returns_no_rows_and_makes_no_request(self):
        with patch(
            "semantica.ingest.sap_ingestor.request_with_ssrf_guard",
        ) as guard:
            ing = SAPIngestor(
                base_url="https://sap.example/odata/",
                username="u",
                password="p",
            )
            result = ing.ingest_entity_set(entity_set="SalesOrderSet", top=0)

        assert result.count == 0
        assert result.records == []
        guard.assert_not_called()

    def test_negative_top_rejected(self):
        ing = SAPIngestor(
            base_url="https://sap.example/odata/",
            username="u",
            password="p",
        )
        with pytest.raises(ValidationError, match="must be >= 0"):
            ing.ingest_entity_set(entity_set="SalesOrderSet", top=-1)

    def test_malformed_rows_container_rejected(self):
        resp = _json_resp(
            {"value": {"not": "a list"}},
            "https://sap.example/odata/SalesOrderSet",
        )
        with patch(
            "semantica.ingest.sap_ingestor.request_with_ssrf_guard",
            return_value=resp,
        ):
            ing = SAPIngestor(
                base_url="https://sap.example/odata/",
                username="u",
                password="p",
            )
            with pytest.raises(ProcessingError, match="no list of rows"):
                ing.ingest_entity_set(entity_set="SalesOrderSet")


class TestExport:
    def test_export_as_documents_flattens_to_graph_builder_shape(self):
        ing = SAPIngestor(
            base_url="https://sap.example/odata/",
            username="u",
            password="p",
        )
        entity = SAPODataEntity(
            records=[{"SalesOrderID": "SO-1", "CustomerID": "C-1"}],
            entity_set="SalesOrderSet",
            count=1,
            service="https://sap.example/odata/",
        )
        docs = ing.export_as_documents(entity)
        assert docs[0]["SalesOrderID"] == "SO-1"
        assert docs[0]["id"] == "SO-1"
        assert docs[0]["source"] == "https://sap.example/odata/"


class TestEntityDocument:
    def test_to_document_adds_source(self):
        ent = SAPODataEntity(
            records=[{"k": "v"}],
            entity_set="S",
            count=1,
            service="https://sap.example/odata/",
        )
        assert ent.to_documents()[0]["source"] == "https://sap.example/odata/"

    def test_to_document_injects_graph_builder_identifier(self):
        ent = SAPODataEntity(
            records=[{"SalesOrderID": "SO-1", "CustomerID": "C-1"}],
            entity_set="SalesOrderSet",
            count=1,
            service="https://sap.example/odata/",
        )
        doc = ent.to_documents()[0]
        assert doc["id"] == "SO-1"
        assert doc["name"] == "SO-1"
        assert doc["SalesOrderID"] == "SO-1"  # original field preserved

    def test_to_document_falls_back_to_entity_set_index(self):
        ent = SAPODataEntity(
            records=[{"GrossAmount": "10.0"}],
            entity_set="SalesOrderSet",
            count=1,
            service="https://sap.example/odata/",
        )
        assert ent.to_documents()[0]["id"] == "SalesOrderSet:0"

    def test_public_import_through_lazy_export(self):
        # __getattr__ should resolve the lazy export once the object is created
        assert callable(SAPODataConnector)
