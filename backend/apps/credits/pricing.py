"""Tarification effective, devis et contrôles communs aux dossiers et simulations."""

from decimal import Decimal, ROUND_HALF_UP

from .amounts import reference_amount


def money(value):
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def quote_pricing(application, *, configuration=None, manual_fees=None):
    from apps.configuration.services import application_configuration
    from apps.configuration.pricing_catalog import RATE_FIELDS
    from .fees import build_legacy_fees_breakdown

    configuration = (
        configuration
        if configuration is not None
        else application_configuration(application)
    )
    pricing = configuration["pricing"]
    tariff, defaults = pricing["tariff"], pricing["product_defaults"]
    configured = tariff["engine"] == "CONFIGURED"
    base = reference_amount(application)
    months = getattr(application, "duration_months", None)
    currency = getattr(application, "currency", "") or defaults["currency"]
    band = None
    if configured and base is not None and months is not None:
        for row in tariff["bands"]:
            if all(
                row[key] is None
                or (
                    value >= Decimal(str(row[key]))
                    if key.startswith("min")
                    else value <= Decimal(str(row[key]))
                )
                for key, value in (
                    ("min_amount", base),
                    ("max_amount", base),
                    ("min_months", Decimal(months)),
                    ("max_months", Decimal(months)),
                )
            ):
                band = row
                break
    failures, rates, proposed = [], {}, {}
    if configured and tariff["currency"] != currency:
        failures.append(
            f"Le barème est en {tariff['currency']} et le dossier en {currency} : aucune conversion implicite n'est autorisée."
        )
    for key, label in RATE_FIELDS.items():
        rule = tariff[key]
        default = band.get(key) if band else None
        if default is None:
            default = rule["default"] if configured else None
        if default is None:
            default = (
                defaults.get(key, "0")
                if (configured or key == "interest_rate")
                else "0"
            )
        proposed[key] = str(default)
        entered = getattr(application, key, None)
        rate = Decimal(str(default if entered is None else entered))
        rates[key] = str(rate)
        if configured:
            if not rule["negotiable"] and rate != Decimal(str(default)):
                failures.append(
                    f"{label} : le taux du barème ({default} %) est obligatoire."
                )
            for bound, comparison in (
                ("min", "inférieur au minimum"),
                ("max", "supérieur au maximum"),
            ):
                limit = rule[bound]
                if limit is not None and (
                    rate < Decimal(limit) if bound == "min" else rate > Decimal(limit)
                ):
                    failures.append(f"{label} : {rate} % est {comparison} ({limit} %).")
    if not configured:
        return {
            "engine": "LEGACY",
            "currency": currency,
            "band": None,
            "rates": rates,
            "defaults": proposed,
            "failures": [],
            "fees": build_legacy_fees_breakdown(application, manual_fees),
            "configuration_fingerprint": configuration["fingerprint"],
        }
    if base is None or base <= 0:
        failures.append(
            "Un montant strictement positif est requis pour la tarification."
        )
    if manual_fees is None:
        manual_fees = (
            list(application.extra_fees.values("label", "mode", "value"))
            if getattr(application, "pk", None)
            else []
        )
    if manual_fees and not tariff["allow_manual_fees"]:
        failures.append(
            "Les frais additionnels saisis manuellement sont interdits par ce barème."
        )
    lines = []

    def add_line(
        code,
        label,
        mode,
        value,
        tax_rate="0",
        floor=None,
        ceiling=None,
        source="TARIFF",
        is_dossier=False,
    ):
        value, tax_rate = Decimal(str(value)), Decimal(str(tax_rate))
        amount = (
            money((base or Decimal("0")) * value / 100)
            if mode == "PERCENT"
            else money(value)
        )
        if floor is not None:
            amount = max(amount, Decimal(floor))
        if ceiling is not None:
            amount = min(amount, Decimal(ceiling))
        tax = money(amount * tax_rate / 100)
        lines.append(
            {
                "id": None,
                "code": code,
                "label": label,
                "mode": mode,
                "value": str(value),
                "amount": str(money(amount + tax)),
                "base_excluding_tax": str(amount),
                "tax_rate": str(tax_rate),
                "tax_amount": str(tax),
                "source": source,
                "is_dossier": is_dossier,
            }
        )

    add_line(
        "PROCESSING",
        "Frais de dossier",
        "PERCENT",
        rates["fees_rate"],
        tariff["processing_tax_rate"],
        is_dossier=True,
    )
    for row in tariff["charges"]:
        add_line(
            row["code"],
            row["label"],
            row["mode"],
            row["value"],
            row["tax_rate"],
            row["min_amount"],
            row["max_amount"],
        )
    for index, row in enumerate(manual_fees):
        add_line(
            f"MANUAL_{index + 1}",
            row["label"],
            row["mode"],
            row["value"],
            source="MANUAL",
        )
    total = money(sum((Decimal(row["amount"]) for row in lines), Decimal("0")))
    taxes = money(sum((Decimal(row["tax_amount"]) for row in lines), Decimal("0")))
    limit = tariff["max_total_fees_pct"]
    if limit is not None and base and total * 100 > base * Decimal(limit):
        failures.append(f"Le total des frais et taxes dépasse {limit} % du capital.")
    if base is not None and total > base:
        failures.append("Le total des frais et taxes dépasse le capital du crédit.")
    return {
        "engine": "CONFIGURED",
        "currency": currency,
        "band": band["id"] if band else None,
        "rates": rates,
        "defaults": proposed,
        "failures": failures,
        "fees": {
            "base_amount": str(base) if base is not None else None,
            "lines": lines,
            "total": str(total),
            "total_taxes": str(taxes),
            "net_after_fees": str(money(base - total)) if base is not None else None,
        },
        "configuration_fingerprint": configuration["fingerprint"],
    }


def assert_pricing(application):
    from apps.workflow.services import WorkflowError

    quote = quote_pricing(application)
    if quote["failures"]:
        raise WorkflowError("Tarification : " + " ".join(quote["failures"]))
    return quote


def materialize_rates(application):
    """Fixe les valeurs héritées avant calcul financier et soumission atomique."""
    quote = assert_pricing(application)
    fields = []
    for key, rate in quote["rates"].items():
        if getattr(application, key) is None and (
            quote["engine"] == "CONFIGURED" or key == "interest_rate"
        ):
            setattr(application, key, Decimal(rate))
            fields.append(key)
    if fields:
        application.save(update_fields=[*fields, "updated_at"])
    return quote


def simulation_pricing(data, user):
    """Contexte hypothétique validé, sans création de dossier ni écriture."""
    from types import SimpleNamespace
    from rest_framework.exceptions import PermissionDenied, ValidationError
    from apps.catalog.models import CreditProduct
    from apps.common.access import user_has_agency_access
    from apps.common.scoped import get_for_tenant
    from apps.common.tenancy import get_current_tenant_id
    from apps.configuration.services import resolve_context
    from apps.tenants.models import Agency

    product = (
        get_for_tenant(CreditProduct, data["product"]) if data.get("product") else None
    )
    if product is not None and not product.is_active:
        raise ValidationError({"product": "Ce produit est inactif."})
    agency_id = data.get("agency") or getattr(user, "agency_id", None)
    if agency_id:
        get_for_tenant(Agency, agency_id)
        if not user_has_agency_access(user, agency_id):
            raise PermissionDenied("Cette agence n'est pas dans votre périmètre.")
    client_type = data.get("client_type") or (
        product.client_type if product and product.client_type != "ALL" else ""
    )
    if product and client_type:
        from .instruction_policy import _product_client_type_ok

        if not _product_client_type_ok(
            SimpleNamespace(
                product=product,
                client=SimpleNamespace(
                    client_type=client_type,
                    is_legal_entity=client_type in {"CORPORATE", "PROFESSIONAL"},
                ),
            )
        ):
            raise ValidationError(
                {"client_type": "Ce type de clientèle ne correspond pas au produit."}
            )
    profile = data.get("individual_profile") or ""
    if profile and client_type != "INDIVIDUAL":
        raise ValidationError(
            {
                "individual_profile": "Un profil particulier nécessite une personne physique."
            }
        )
    if data.get("annual_rate") is None and product is None:
        raise ValidationError(
            {"annual_rate": "Indiquez un taux ou sélectionnez un produit."}
        )
    configuration = resolve_context(
        get_current_tenant_id(),
        {
            "product": str(product.pk) if product else "",
            "agency": str(agency_id or ""),
            "client_type": client_type,
            "individual_profile": profile,
        },
    )
    application = SimpleNamespace(
        status="DRAFT",
        amount_requested=data["amount"],
        duration_months=data["months"],
        product=product,
        interest_rate=data.get("annual_rate"),
        fees_rate=data.get("fees_rate"),
        mandatory_savings_rate=data.get("savings_rate"),
        currency=data.get("currency") or (product.currency if product else "XOF"),
    )
    if product:
        from .instruction_policy import assert_product_bounds
        from apps.workflow.services import WorkflowError

        try:
            assert_product_bounds(application)
        except WorkflowError as exc:
            raise ValidationError({"product": str(exc)}) from exc
    quote = quote_pricing(
        application,
        configuration=configuration,
        manual_fees=data.get("extra_fees") or [],
    )
    if quote["failures"]:
        raise ValidationError({"pricing": quote["failures"]})
    from .simulation import conventions_for_application
    quote["simulation_conventions"] = conventions_for_application(application, configuration)
    return quote
