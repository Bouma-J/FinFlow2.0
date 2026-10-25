"""Alignement modèles de contrats ↔ fiche client (groupement, famille, emploi)."""
from datetime import date
from decimal import Decimal

import pytest

from apps.clients.models import Client, ClientPhone
from apps.common.tenancy import tenant_context
from apps.contracts.context import VARIABLE_CATALOG, build_context
from apps.contracts.models import ContractTemplate
from apps.credits.models import CreditApplication
from apps.tenants.models import Agency

pytestmark = pytest.mark.django_db


def _app(tenant, client, product, **extra):
    return CreditApplication.objects.create(
        tenant=tenant,
        reference=extra.pop("reference", "D-CTX"),
        client=client,
        product=product,
        amount_requested=Decimal("500000"),
        duration_months=12,
        **extra,
    )


def _template(*, applies_to):
    return ContractTemplate(applies_to=applies_to, is_active=True, name="T")


def test_groupement_uses_corporate_templates(tenant_a, product_a):
    with tenant_context(tenant_a.id):
        groupement = Client.objects.create(
            tenant=tenant_a,
            client_type=Client.ClientType.PROFESSIONAL,
            company_name="GIE Maraîchers",
        )
        application = _app(tenant_a, groupement, product_a)
        assert _template(
            applies_to=ContractTemplate.AppliesTo.CORPORATE
        ).applies_to_application(application)
        assert not _template(
            applies_to=ContractTemplate.AppliesTo.INDIVIDUAL
        ).applies_to_application(application)
        assert _template(
            applies_to=ContractTemplate.AppliesTo.ANY
        ).applies_to_application(application)


def test_individual_still_excluded_from_corporate_templates(
    tenant_a, product_a, client_a
):
    with tenant_context(tenant_a.id):
        application = _app(tenant_a, client_a, product_a, reference="D-IND")
        assert not _template(
            applies_to=ContractTemplate.AppliesTo.CORPORATE
        ).applies_to_application(application)
        assert _template(
            applies_to=ContractTemplate.AppliesTo.INDIVIDUAL
        ).applies_to_application(application)


def test_corporate_still_matches_corporate_templates(tenant_a, product_a):
    with tenant_context(tenant_a.id):
        company = Client.objects.create(
            tenant=tenant_a,
            client_type=Client.ClientType.CORPORATE,
            company_name="SARL Demo",
        )
        application = _app(tenant_a, company, product_a, reference="D-ENT")
        assert _template(
            applies_to=ContractTemplate.AppliesTo.CORPORATE
        ).applies_to_application(application)
        assert not _template(
            applies_to=ContractTemplate.AppliesTo.INDIVIDUAL
        ).applies_to_application(application)


def test_client_type_label_and_family_phones_employment(tenant_a, product_a):
    with tenant_context(tenant_a.id):
        client_agency = Agency.objects.create(
            tenant=tenant_a, code="CLI01", name="Agence Client"
        )
        dossier_agency = Agency.objects.create(
            tenant=tenant_a, code="DOS01", name="Agence Dossier"
        )
        client = Client.objects.create(
            tenant=tenant_a,
            client_type=Client.ClientType.INDIVIDUAL,
            first_name="Awa",
            last_name="Diop",
            phone="77000001",
            country="Sénégal",
            birth_country="Mali",
            agency=client_agency,
            spouse_last_name="Ndiaye",
            spouse_first_name="Moussa",
            spouse_phone="77000002",
            spouse_profession="Commerçant",
            father_last_name="Diop",
            father_first_name="Ibrahima",
            mother_last_name="Fall",
            mother_first_name="Fatou",
            kyc_status=Client.KycStatus.VALIDATED,
            kyc_validated_at=date(2026, 1, 15),
        )
        ClientPhone.objects.create(
            tenant=tenant_a, client=client, number="77000003", label="Bureau"
        )
        ClientPhone.objects.create(
            tenant=tenant_a, client=client, number="77000004", label="WhatsApp"
        )
        application = _app(
            tenant_a,
            client,
            product_a,
            reference="D-FAM",
            agency=dossier_agency,
            employer_name="SONATEL",
            contract_type="CDI",
            dependents_count=3,
            salary_domiciliation=True,
        )
        ctx = build_context(application)

        assert ctx["client_type"] == "Particulier"
        assert ctx["client_pays"] == "Sénégal"
        assert ctx["client_lieu_naissance"] == "Mali"
        assert ctx["client_pays_naissance"] == "Mali"
        assert ctx["client_conjoint_nom"] == "Ndiaye"
        assert ctx["client_conjoint_prenom"] == "Moussa"
        assert ctx["client_conjoint_nom_complet"] == "Moussa Ndiaye"
        assert ctx["client_conjoint_telephone"] == "77000002"
        assert ctx["client_conjoint_profession"] == "Commerçant"
        assert ctx["client_pere_nom_complet"] == "Ibrahima Diop"
        assert ctx["client_mere_nom_complet"] == "Fatou Fall"
        assert ctx["client_telephone"] == "77000001"
        assert ctx["client_telephone2"] == "77000003"
        assert ctx["client_telephone3"] == "77000004"
        assert "77000001" in ctx["client_telephones"]
        assert "77000003" in ctx["client_telephones"]
        assert "Bureau" in ctx["client_telephones_autres"]
        assert ctx["client_kyc"] == "Validé"
        assert ctx["client_kyc_valide_le"] == "15/01/2026"
        assert ctx["client_agence_nom"] == "Agence Client"
        assert ctx["client_agence_code"] == "CLI01"
        assert ctx["agence_nom"] == "Agence Dossier"
        assert ctx["employeur"] == "SONATEL"
        assert ctx["type_contrat"] == "CDI"
        assert ctx["personnes_a_charge"] == 3
        assert ctx["domiciliation_salaire"] == "Oui"


def test_groupement_client_type_label(tenant_a, product_a):
    with tenant_context(tenant_a.id):
        groupement = Client.objects.create(
            tenant=tenant_a,
            client_type=Client.ClientType.PROFESSIONAL,
            company_name="GIE Cacao",
        )
        ctx = build_context(_app(tenant_a, groupement, product_a, reference="D-GRP"))
        assert ctx["client_type"] == "Groupement"
        assert ctx["client_nom_complet"] == "GIE Cacao"


def test_corporate_client_type_label_unchanged(tenant_a, product_a):
    with tenant_context(tenant_a.id):
        company = Client.objects.create(
            tenant=tenant_a,
            client_type=Client.ClientType.CORPORATE,
            company_name="SARL Demo",
        )
        ctx = build_context(_app(tenant_a, company, product_a, reference="D-COR"))
        assert ctx["client_type"] == "Entreprise"


def test_catalog_exposes_new_client_tags():
    items = {
        key
        for group in VARIABLE_CATALOG
        for key, _label in group["items"]
    }
    for key in (
        "client_pays",
        "client_pays_naissance",
        "client_telephones",
        "client_conjoint_nom_complet",
        "client_pere_nom",
        "client_mere_prenom",
        "client_kyc",
        "client_agence_nom",
        "employeur",
        "type_contrat",
        "personnes_a_charge",
        "domiciliation_salaire",
    ):
        assert key in items
