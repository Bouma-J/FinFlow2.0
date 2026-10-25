"""Import du portefeuille CBS → prêts + dossiers de recouvrement."""
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.collections.models import CollectionCase, CollectionTranche
from apps.common.tenancy import tenant_context
from apps.corebanking.models import CoreBankingConnector
from apps.corebanking.portfolio_import import (
    enqueue_initial_portfolio_import,
    import_cbs_portfolio,
    is_live_cbs_connector,
    parse_cbs_dossier_refs,
)
from apps.corebanking.services import (
    RestAdapter,
    default_simulated_overdue_portfolio,
    list_cbs_outstanding_credits,
)
from apps.credits.models import Loan

pytestmark = pytest.mark.django_db


@pytest.fixture
def sim_connector(tenant_a):
    with tenant_context(tenant_a.id):
        return CoreBankingConnector.objects.create(
            tenant=tenant_a,
            name="CBS Simulate",
            protocol=CoreBankingConnector.Protocol.REST,
            base_url="",
            mapping_rules={"force_simulate": True, "simulate": {}},
            is_active=True,
        )


def test_list_simulated_default_portfolio(tenant_a, sim_connector):
    with tenant_context(tenant_a.id):
        result = list_cbs_outstanding_credits(tenant_a.id)
    refs = {row["loan_ref"] for row in result["credits"]}
    expected = {row["refDemande"] for row in default_simulated_overdue_portfolio()}
    assert refs == expected
    days = {row["loan_ref"]: row["days_overdue"] for row in result["credits"]}
    assert days["CBS-IMP-GEST-001"] == 15
    assert days["CBS-IMP-REC-002"] == 45
    assert days["CBS-IMP-JUR-003"] == 110


def test_import_creates_cases_in_correct_tranches(tenant_a, sim_connector):
    with tenant_context(tenant_a.id):
        stats = import_cbs_portfolio(tenant_a.id, connector=sim_connector)
        assert stats["loans_created"] == 3
        assert stats["cases_opened"] == 3
        assert stats["errors"] == []

        by_ref = {
            loan.cbs_demande_ref: loan.collection_case
            for loan in Loan.objects.select_related("collection_case__tranche")
        }
        assert by_ref["CBS-IMP-GEST-001"].tranche.owner_kind == (
            CollectionTranche.OwnerKind.GESTIONNAIRE
        )
        assert by_ref["CBS-IMP-GEST-001"].stage == CollectionCase.Stage.AMICABLE
        assert by_ref["CBS-IMP-REC-002"].tranche.owner_kind == (
            CollectionTranche.OwnerKind.COLLECTION
        )
        assert by_ref["CBS-IMP-REC-002"].stage == CollectionCase.Stage.PRECONTENTIOUS
        assert by_ref["CBS-IMP-JUR-003"].tranche.owner_kind == (
            CollectionTranche.OwnerKind.LEGAL
        )
        assert by_ref["CBS-IMP-JUR-003"].stage == CollectionCase.Stage.LITIGATION


def test_import_is_idempotent(tenant_a, sim_connector):
    with tenant_context(tenant_a.id):
        first = import_cbs_portfolio(tenant_a.id, connector=sim_connector)
        second = import_cbs_portfolio(tenant_a.id, connector=sim_connector)
        assert first["loans_created"] == 3
        assert second["loans_created"] == 0
        assert second["loans_updated"] == 3
        assert Loan.objects.count() == 3
        assert CollectionCase.objects.count() == 3


def test_is_live_cbs_connector_requires_url_and_cbs_mode(tenant_a):
    with tenant_context(tenant_a.id):
        empty = CoreBankingConnector.objects.create(
            tenant=tenant_a,
            name="Empty",
            protocol="REST",
            base_url="",
            mapping_rules={"disbursement": {"mode": "CBS"}, "force_simulate": False},
            is_active=True,
        )
        live = CoreBankingConnector.objects.create(
            tenant=tenant_a,
            name="Live",
            protocol="REST",
            base_url="https://serveur-api",
            mapping_rules={"disbursement": {"mode": "CBS"}, "force_simulate": False},
            is_active=True,
        )
        local = CoreBankingConnector.objects.create(
            tenant=tenant_a,
            name="Local",
            protocol="REST",
            base_url="https://serveur-api",
            mapping_rules={"disbursement": {"mode": "LOCAL"}, "force_simulate": True},
            is_active=True,
        )
    assert is_live_cbs_connector(empty) is False
    assert is_live_cbs_connector(live) is True
    assert is_live_cbs_connector(local) is False


def test_enqueue_initial_import_only_once(tenant_a):
    with tenant_context(tenant_a.id):
        connector = CoreBankingConnector.objects.create(
            tenant=tenant_a,
            name="Live once",
            protocol="REST",
            base_url="https://serveur-api",
            mapping_rules={"disbursement": {"mode": "CBS"}, "force_simulate": False},
            is_active=True,
        )
        with patch(
            "apps.corebanking.tasks.import_cbs_portfolio_task.delay"
        ) as delay:
            first = enqueue_initial_portfolio_import(connector)
            second = enqueue_initial_portfolio_import(connector)
        assert first is not None
        assert second is None
        delay.assert_called_once()
        connector.refresh_from_db()
        assert connector.mapping_rules.get("portfolio_import_started_at")


def test_rest_adapter_crd_impayes_maps_rows(tenant_a):
    with tenant_context(tenant_a.id):
        conn = CoreBankingConnector.objects.create(
            tenant=tenant_a,
            name="REST impayes",
            protocol="REST",
            base_url="https://serveur-api",
            mapping_rules={
                "endpoints": {"crd_impayes": "gateway-perfect/crd/impayes"},
            },
            auth_config={"access_token": "TOK"},
            is_active=True,
        )
    adapter = RestAdapter(conn)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = b"{}"
    mock_resp.json.return_value = {
        "responseCode": 200,
        "datas": [
            {
                "refDemande": "REF-IMP-1",
                "numContrat": "CTR-1",
                "codeAdherent": "A55",
                "nomAdherent": "Koffi",
                "joursRetard": 40,
                "montantImpaye": 12000,
                "montant": 100000,
            }
        ],
    }
    with patch("requests.post", return_value=mock_resp) as post:
        result = adapter.send("LIST_OVERDUE_CREDITS", {"overdue_only": True})
    assert result["credits"][0]["loan_ref"] == "REF-IMP-1"
    assert result["credits"][0]["days_overdue"] == 40
    args, kwargs = post.call_args
    assert kwargs["url"].endswith("gateway-perfect/crd/impayes")
    assert kwargs["headers"]["Authorization"] == "Bearer TOK"


def test_api_import_portfolio_sync(tenant_a, sim_connector, product_a):
    user = User.objects.create_user(
        username="cbs_admin",
        password="test-pass-123",
        tenant=None,
        is_group_level=True,
        is_staff=True,
        is_superuser=True,
    )
    api = APIClient()
    api.force_authenticate(user=user)
    api.credentials(HTTP_X_TENANT_ID=str(tenant_a.id))
    response = api.post(
        f"/api/v1/cbs-connectors/{sim_connector.id}/import-portfolio/?sync=1"
    )
    assert response.status_code == 200
    assert response.data["loans_created"] == 3
    assert response.data["cases_opened"] == 3
    with tenant_context(tenant_a.id):
        assert CollectionCase.objects.count() == 3


def test_parse_xlsx_and_csv_dossier_refs():
    from django.core.files.uploadedfile import SimpleUploadedFile
    from openpyxl import Workbook

    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["Numéro de dossier"])
    sheet.append(["CBS-IMP-GEST-001"])
    sheet.append(["CBS-IMP-REC-002"])
    sheet.append(["CBS-IMP-GEST-001"])
    buffer = BytesIO()
    workbook.save(buffer)
    xlsx = SimpleUploadedFile(
        "dossiers.xlsx",
        buffer.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    assert parse_cbs_dossier_refs(xlsx) == [
        "CBS-IMP-GEST-001",
        "CBS-IMP-REC-002",
    ]

    csv_file = SimpleUploadedFile(
        "dossiers.csv",
        b"reference\nCBS-IMP-JUR-003\n\nCBS-IMP-JUR-003\n",
        content_type="text/csv",
    )
    assert parse_cbs_dossier_refs(csv_file) == ["CBS-IMP-JUR-003"]


def test_import_from_file_refs_calls_situation(tenant_a, sim_connector):
    with tenant_context(tenant_a.id):
        stats = import_cbs_portfolio(
            tenant_a.id,
            connector=sim_connector,
            loan_refs=["CBS-IMP-REC-002", "CBS-IMP-JUR-003"],
        )
        assert stats["source"] == "file"
        assert stats["discovered"] == 2
        assert stats["loans_created"] == 2
        assert stats["cases_opened"] == 2
        owners = set(
            CollectionCase.objects.values_list("tranche__owner_kind", flat=True)
        )
        assert owners == {
            CollectionTranche.OwnerKind.COLLECTION,
            CollectionTranche.OwnerKind.LEGAL,
        }


def test_api_import_portfolio_from_csv(tenant_a, sim_connector):
    from django.core.files.uploadedfile import SimpleUploadedFile

    user = User.objects.create_user(
        username="cbs_file_admin",
        password="test-pass-123",
        tenant=None,
        is_group_level=True,
        is_staff=True,
        is_superuser=True,
    )
    api = APIClient()
    api.force_authenticate(user=user)
    api.credentials(HTTP_X_TENANT_ID=str(tenant_a.id))
    upload = SimpleUploadedFile(
        "refs.csv",
        b"CBS-IMP-GEST-001\n",
        content_type="text/csv",
    )
    response = api.post(
        f"/api/v1/cbs-connectors/{sim_connector.id}/import-portfolio/?sync=1",
        {"file": upload},
        format="multipart",
    )
    assert response.status_code == 200, response.data
    assert response.data["source"] == "file"
    assert response.data["loans_created"] == 1
    assert response.data["cases_opened"] == 1


def test_import_cbs_list_error_is_validation_error(tenant_a, sim_connector):
    from rest_framework.exceptions import ValidationError

    from apps.corebanking.services import CoreBankingError

    with tenant_context(tenant_a.id):
        with patch(
            "apps.corebanking.portfolio_import.list_cbs_outstanding_credits",
            side_effect=CoreBankingError("CBS indisponible"),
        ):
            with pytest.raises(ValidationError, match="CBS indisponible"):
                import_cbs_portfolio(tenant_a.id, connector=sim_connector)


def test_api_import_portfolio_cbs_error_is_400(tenant_a, sim_connector):
    from apps.corebanking.services import CoreBankingError

    user = User.objects.create_user(
        username="cbs_err_admin",
        password="test-pass-123",
        tenant=None,
        is_group_level=True,
        is_staff=True,
        is_superuser=True,
    )
    api = APIClient()
    api.force_authenticate(user=user)
    api.credentials(HTTP_X_TENANT_ID=str(tenant_a.id))
    with patch(
        "apps.corebanking.portfolio_import.list_cbs_outstanding_credits",
        side_effect=CoreBankingError("CBS indisponible"),
    ):
        response = api.post(
            f"/api/v1/cbs-connectors/{sim_connector.id}/import-portfolio/?sync=1",
        )
    assert response.status_code == 400, response.data
    errors = response.data.get("errors") or response.data
    detail = errors.get("detail") if isinstance(errors, dict) else None
    assert "CBS indisponible" in str(detail or errors)


def test_import_task_catches_connector_failure(tenant_a, sim_connector):
    from apps.corebanking.services import CoreBankingError
    from apps.corebanking.tasks import import_cbs_portfolio_task

    with patch(
        "apps.corebanking.portfolio_import.import_cbs_portfolio",
        side_effect=CoreBankingError("CBS down"),
    ):
        stats = import_cbs_portfolio_task.run(
            str(tenant_a.id), str(sim_connector.id)
        )
    assert stats["errors"]
    assert "interrompu" in stats["errors"][0]["error"]
