"""Résolution commune des références affichées, autorisées et envoyées au CBS."""
from .models import CbsManager, CbsProductReference, Currency, FinancingObject, LoanPeriodicity, RepaymentMethod, ServicePoint


DEMO_PRODUCT_CODES = {
    "CRED-TRESO", "CRED-TRESO-PRO", "CRED-IMMO", "CRED-IMMO-PROMO",
    "CRED-CONSO", "CRED-EQUIP", "CRED-AGRO", "COMPTE-COURANT",
}


def is_demo_product_code(value):
    return str(value or "").strip().upper() in DEMO_PRODUCT_CODES


def resolve_application_cbs(application, *, connector=None):
    from apps.corebanking.services import CoreBankingError, resolve_active_connector
    from .cbs_resolve import resolve_ref, resolve_financing_object_cbs, resolve_repayment_cbs
    from .models import RepaymentMethod

    tid = application.tenant_id
    if connector is None:
        try:
            connector = resolve_active_connector(tid)
        except CoreBankingError:
            connector = None
    rules = (connector.mapping_rules or {}) if connector else {}
    disb = rules.get("disbursement") or {}
    defaults = disb.get("defaults") or {}
    requires_real = bool(connector and not rules.get("force_simulate") and str(disb.get("mode", "CBS")).upper() != "LOCAL")
    live = bool(connector and connector.is_active and connector.protocol == "REST"
                and connector.base_url.strip() and not rules.get("force_simulate")
                and str(disb.get("mode") or "CBS").upper() == "CBS")
    errors = []

    def error(field, message):
        errors.append({"field": field, "message": message})

    if connector is None:
        error("connector", "Aucun connecteur CBS actif pour cette filiale.")
    elif str(connector.tenant_id) != str(tid):
        error("connector", "Le connecteur CBS appartient à une autre filiale.")
    if requires_real and not live:
        error("connector", "La mise en place réelle exige un connecteur REST actif avec une URL CBS.")

    period = resolve_ref(LoanPeriodicity, tid, application.periodicity or "")
    curr = resolve_ref(Currency, tid, application.currency or "")
    mechanism = resolve_ref(RepaymentMethod, tid, application.repayment_mechanism or "")
    if not period.get("cbs_code"):
        error("periodicity", "Sélectionnez une périodicité active importée du CBS.")
    if not curr.get("cbs_code"):
        error("currency", "Sélectionnez une devise active importée du CBS.")
    if live and not mechanism.get("cbs_code"):
        error("repayment_mechanism", "Sélectionnez un mécanisme d'amortissement actif avec son identifiant CBS (idProduitRemb).")

    obj = None
    selected = getattr(application, "financing_object_id", None)
    if selected:
        obj = FinancingObject.all_tenants.filter(pk=selected, tenant_id=tid, is_active=True).exclude(cbs_code="").first()
        if not obj:
            error("financing_object", "L'objet CBS sélectionné est absent, inactif ou hors filiale.")
    else:
        # Compatibilité des anciens dossiers : uniquement une correspondance
        # explicite du connecteur ou un objet métier unique, jamais le premier.
        mapped = str((disb.get("purpose_map") or {}).get(application.purpose_type) or "").strip()
        matches = FinancingObject.all_tenants.filter(tenant_id=tid, is_active=True).exclude(cbs_code="")
        candidates = list(matches.filter(cbs_code=mapped)[:2]) if mapped else []
        if not candidates and application.purpose_type:
            candidates = list(matches.filter(purpose_type=application.purpose_type)[:2])
        if len(candidates) == 1:
            obj = candidates[0]
        elif live:
            error("financing_object", "Sélectionnez l'objet de financement CBS exact ; aucune correspondance unique n'est disponible.")
    financing = {"id": str(obj.pk), "code": obj.code, "label": obj.label, "cbs_code": obj.cbs_code.strip(), "purpose_type": obj.purpose_type} if obj else {}
    if not financing and not live and not selected:
        value = resolve_financing_object_cbs(tid, application.purpose_type, purpose_map=disb.get("purpose_map"), default=defaults.get("idObjetFinancement", ""))
        if value:
            financing = {"code": application.purpose_type, "label": application.purpose_type, "cbs_code": value}

    product = getattr(application, "product", None)
    if product and (str(product.tenant_id) != str(tid) or not product.is_active):
        error("product", "Le produit local doit être actif et appartenir à la filiale.")
    if product and product.currency != application.currency:
        error("currency", "La devise du dossier ne correspond pas à celle du produit local.")
    products = {}
    if requires_real:
        # CBS ne fournit pas de catalogue crédit exploitable : l'ID est saisi
        # directement sur le produit local. Ne jamais le déduire de l'objet.
        credit_code = (getattr(product, "cbs_product_code", "") or "").strip()
        credit_source = "credit_product.cbs_product_code"
        if not credit_code or is_demo_product_code(credit_code):
            # Compatibilité avec les produits déjà associés à une référence
            # CBS confirmée avant l'introduction de la saisie directe.
            pk = getattr(product, "cbs_credit_product_id", None)
            ref = CbsProductReference.all_tenants.filter(pk=pk, tenant_id=tid).first() if pk else None
            valid_legacy_ref = bool(
                ref and ref.kind == "CREDIT" and ref.is_active
                and ref.verification_status == "VERIFIED" and ref.verified_at
                and ref.verified_by_id and ref.source_reference.strip()
                and ref.cbs_code.strip() and not is_demo_product_code(ref.cbs_code)
                and connector and ref.connector_id == connector.pk
                and (not ref.currency or ref.currency == application.currency)
            )
            if valid_legacy_ref:
                credit_code = ref.cbs_code.strip()
                credit_source = "legacy_confirmed_reference"

        if credit_code and not is_demo_product_code(credit_code):
            products["cbs_credit_product"] = {
                "cbs_code": credit_code,
                "source": credit_source,
            }
        else:
            products["cbs_credit_product"] = {}
            error("product.cbs_product_code", "Saisissez l'identifiant CBS réel idProduitCrd dans le produit local ; il est distinct de l'objet de financement du dossier.")
        products["cbs_repayment_product"] = {**mechanism, "source": "repayment_methods"}
    else:
        # Compatibilité des scénarios explicitement locaux existants.
        for field, kind in (("cbs_credit_product", "CREDIT"), ("cbs_repayment_product", "REPAYMENT")):
            value = (getattr(product, "cbs_product_code" if kind == "CREDIT" else "cbs_repayment_product_code", "") or "").strip()
            if not value and kind == "REPAYMENT":
                value = resolve_repayment_cbs(tid, application.repayment_mechanism) or str(defaults.get("idProduitRemb") or "")
            if not value and kind == "CREDIT":
                value = str(defaults.get("idProduitCrd") or getattr(product, "code", ""))
            products[field] = {"cbs_code": value, "simulated": True}

    point = (getattr(getattr(application, "agency", None), "cbs_point_of_service_id", "") or str(defaults.get("idPointService") or "")).strip()
    if application.agency_id and str(application.agency.tenant_id) != str(tid):
        error("agency", "L'agence appartient à une autre filiale.")
    manager = ""
    for actor in (getattr(application, "submitted_by", None), getattr(application, "created_by", None)):
        if actor and str(actor.tenant_id) == str(tid) and (actor.cbs_id or "").strip():
            manager = actor.cbs_id.strip()
            break
    if not manager:
        manager = str(defaults.get("idGestionnaire") or "").strip()
    if not point or (live and not ServicePoint.all_tenants.filter(tenant_id=tid, cbs_code=point, is_active=True).exists()):
        error("agency.cbs_point_of_service_id", "Associez l'agence à un point de service CBS actif de la filiale.")
    if not manager or (live and not CbsManager.all_tenants.filter(tenant_id=tid, cbs_code=manager, is_active=True).exists()):
        error("submitted_by.cbs_id", "Associez le soumissionnaire à un gestionnaire CBS actif de la filiale.")
    client = getattr(application, "client", None)
    if not client or str(client.tenant_id) != str(tid):
        error("client", "Le client doit appartenir à la filiale du dossier.")
    code = (getattr(client, "cbs_client_id", "") or "").strip()
    account = (getattr(client, "cbs_account_number", "") or "").strip()
    identity = (getattr(client, "national_id", "") or "").strip()
    if not (code or account or identity):
        error("client.cbs_client_id", "Renseignez un identifiant adhérent ou compte CBS sur le client.")
    values = {
        "idPeriodicite": period.get("cbs_code", ""), "codeDevise": curr.get("cbs_code", ""),
        "idObjetFinancement": financing.get("cbs_code", ""),
        "idProduitCrd": products["cbs_credit_product"].get("cbs_code", ""),
        "idProduitRemb": products["cbs_repayment_product"].get("cbs_code", ""),
        "idPointService": point, "idGestionnaire": manager,
        "codeAdherent": code, "numManuel": account, "numPieceIdentite": identity,
    }
    if requires_real:
        # Les identifiants sont des alternatives de recherche, pas des
        # compléments KYC. Ne pas envoyer une pièce locale fictive lorsqu'un
        # code adhérent CBS est déjà disponible.
        if code:
            values.update(numManuel="", numPieceIdentite="")
        elif account:
            values["numPieceIdentite"] = ""
    return {"periodicity": period, "repayment_method": mechanism, "currency": curr, "financing_object": financing,
            "credit_product": products["cbs_credit_product"], "repayment_product": products["cbs_repayment_product"],
            "product_cbs_code": values["idProduitCrd"], "product_repayment_cbs_code": values["idProduitRemb"],
            "manager_cbs_id": manager, "client_adherent_id": code or account or identity, "point_of_service_id": point,
            "connector_id": str(connector.pk) if connector else None, "live_mode": live, "requires_real": requires_real, "values": values,
            "errors": errors, "warnings": [e["message"] for e in errors], "ready_for_cbs": not errors}


def assert_application_cbs_mapping(application, *, connector=None):
    from apps.corebanking.services import CoreBankingError

    resolved = resolve_application_cbs(application, connector=connector)
    tenant_errors = any(e["field"] in {"connector", "client", "product", "agency"} for e in resolved["errors"])
    if resolved["errors"] and (resolved["requires_real"] or not resolved["connector_id"] or tenant_errors):
        raise CoreBankingError("Correspondances CBS incomplètes : " + " ; ".join(
            f"{e['field']} : {e['message']}" for e in resolved["errors"]
        ))
    return resolved


def cbs_mapping_snapshot(application):
    """Preuve stable des valeurs et confirmations, contrôlée à l'exécution."""
    resolved = resolve_application_cbs(application)
    return {"connector_id": resolved["connector_id"], "values": resolved["values"],
            "identifier_policy": "PRIMARY_CBS_IDENTIFIER" if resolved["requires_real"] else "LOCAL_LEGACY",
            "mapping_contract": "MANUAL_CREDIT_PRODUCT_ID_FINANCING_OBJECT_REPAYMENT_METHOD_V3" if resolved["requires_real"] else "LOCAL_LEGACY",
            "credit_product": resolved["credit_product"], "repayment_product": resolved["repayment_product"],
            "financing_object_id": resolved["financing_object"].get("id")}


def lock_application_cbs_mapping(application):
    """Stabilise les lignes de paramétrage pendant une autorisation/transmission.

    Les points d'entrée métier sont transactionnels. Les appels de diagnostic
    hors transaction restent en lecture seule.
    """
    from django.db import connection
    from apps.corebanking.models import CoreBankingConnector
    from .models import CreditProduct

    if not connection.in_atomic_block:
        return
    product = CreditProduct.all_tenants.select_for_update().filter(pk=application.product_id, tenant_id=application.tenant_id).first()
    if product:
        application.product = product
        list(CbsProductReference.all_tenants.select_for_update().filter(
            tenant_id=application.tenant_id, pk=product.cbs_credit_product_id))
    resolved = resolve_application_cbs(application)
    obj_id = resolved["financing_object"].get("id")
    if obj_id:
        list(FinancingObject.all_tenants.select_for_update().filter(pk=obj_id, tenant_id=application.tenant_id))
    for model, field, value in (
        (Currency, "code", application.currency), (LoanPeriodicity, "code", application.periodicity),
        (RepaymentMethod, "code", application.repayment_mechanism),
        (CbsManager, "cbs_code", resolved["manager_cbs_id"]), (ServicePoint, "cbs_code", resolved["point_of_service_id"]),
    ):
        list(model.all_tenants.select_for_update().filter(tenant_id=application.tenant_id, **{field: value}).order_by("pk"))
    # Les imports d'objets prennent aussi leur verrou avant celui du connecteur.
    if resolved["connector_id"]:
        list(CoreBankingConnector.all_tenants.select_for_update().filter(pk=resolved["connector_id"]))
