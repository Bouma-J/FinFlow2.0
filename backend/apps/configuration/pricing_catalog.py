"""Barèmes tarifaires déclaratifs, sans formule exécutable ni taux réglementaire implicite."""

from copy import deepcopy
from decimal import Decimal, InvalidOperation
import re

from django.core.exceptions import ValidationError

RATE_FIELDS = {
    "interest_rate": "Taux annuel",
    "fees_rate": "Frais de dossier",
    "mandatory_savings_rate": "Épargne par échéance",
}
DEFAULT_TARIFF = {
    "engine": "LEGACY",
    "currency": "",
    "bands": [],
    "charges": [],
    "allow_manual_fees": True,
    "max_total_fees_pct": None,
    "processing_tax_rate": "0",
    **{
        key: {"default": None, "min": None, "max": None, "negotiable": True}
        for key in RATE_FIELDS
    },
}


def pricing_defaults(product=None):
    return {
        "tariff": deepcopy(DEFAULT_TARIFF),
        "product_defaults": {
            "interest_rate": str(product.interest_rate) if product else "0",
            "fees_rate": str(product.processing_fee_rate) if product else "0",
            "currency": product.currency if product else "",
        },
    }


def number(value, *, maximum="999.999", places=3, nullable=True):
    if value is None and nullable:
        return None
    try:
        if isinstance(value, bool) or value is None:
            raise ValueError
        result = Decimal(str(value))
        if (
            not result.is_finite()
            or result < 0
            or result > Decimal(maximum)
            or result.as_tuple().exponent < -places
        ):
            raise ValueError
    except (InvalidOperation, ValueError, TypeError):
        raise ValidationError(
            "Nombre tarifaire invalide, négatif, hors limites ou trop précis."
        )
    return str(result)


def validate_pricing(value):
    if not isinstance(value, dict) or set(value) - {"tariff"}:
        raise ValidationError("Paramètres de tarification inconnus.")
    if "tariff" not in value:
        return {}
    raw = value["tariff"]
    if not isinstance(raw, dict) or set(raw) - set(DEFAULT_TARIFF):
        raise ValidationError("Barème tarifaire invalide ou champs inconnus.")
    tariff = deepcopy(DEFAULT_TARIFF) | raw
    if not isinstance(tariff["engine"], str) or tariff["engine"] not in {
        "LEGACY",
        "CONFIGURED",
    }:
        raise ValidationError("Moteur de tarification invalide.")
    currency = tariff["currency"]
    if (
        not isinstance(currency, str)
        or (currency and not re.fullmatch(r"[A-Z]{3}", currency))
        or (tariff["engine"] == "CONFIGURED" and not currency)
    ):
        raise ValidationError(
            "Précisez une devise de trois lettres pour le barème configuré."
        )
    for key in RATE_FIELDS:
        row = tariff[key]
        if not isinstance(row, dict) or set(row) - {
            "default",
            "min",
            "max",
            "negotiable",
        }:
            raise ValidationError(f"Paramètres invalides pour {key}.")
        row = deepcopy(DEFAULT_TARIFF[key]) | row
        limit = "999.999" if key == "interest_rate" else "100"
        for field in ("default", "min", "max"):
            row[field] = number(row[field], maximum=limit)
        if not isinstance(row["negotiable"], bool):
            raise ValidationError("Le caractère négociable doit être un booléen.")
        if (
            row["min"] is not None
            and row["max"] is not None
            and Decimal(row["min"]) > Decimal(row["max"])
        ):
            raise ValidationError("Le minimum tarifaire dépasse le maximum.")
        if row["default"] is not None and any(
            row[bound] is not None
            and (
                Decimal(row["default"]) < Decimal(row[bound])
                if bound == "min"
                else Decimal(row["default"]) > Decimal(row[bound])
            )
            for bound in ("min", "max")
        ):
            raise ValidationError("Le taux par défaut est hors des bornes du barème.")
        tariff[key] = row
    if not isinstance(tariff["allow_manual_fees"], bool):
        raise ValidationError("L'autorisation des frais manuels doit être un booléen.")
    tariff["max_total_fees_pct"] = number(tariff["max_total_fees_pct"], maximum="100")
    tariff["processing_tax_rate"] = number(
        tariff["processing_tax_rate"], maximum="100", nullable=False
    )
    for collection, maximum in (("bands", 50), ("charges", 30)):
        if (
            not isinstance(tariff[collection], list)
            or len(tariff[collection]) > maximum
        ):
            raise ValidationError(
                f"La liste {collection} est limitée à {maximum} lignes."
            )
    identifiers = set()
    bands = []
    for row in tariff["bands"]:
        keys = {
            "id",
            "min_amount",
            "max_amount",
            "min_months",
            "max_months",
            *RATE_FIELDS,
        }
        if not isinstance(row, dict) or set(row) - keys:
            raise ValidationError("Tranche tarifaire invalide.")
        identifier = row.get("id")
        if (
            not isinstance(identifier, str)
            or not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", identifier)
            or identifier in identifiers
        ):
            raise ValidationError(
                "Chaque tranche doit avoir un identifiant court et unique."
            )
        identifiers.add(identifier)
        cleaned = {"id": identifier}
        for key in ("min_amount", "max_amount"):
            cleaned[key] = number(row.get(key), maximum="9999999999999999.99", places=2)
        for key in ("min_months", "max_months"):
            result = row.get(key)
            if result is not None and (
                type(result) is not int or not 1 <= result <= 600
            ):
                raise ValidationError(
                    "Les durées d'une tranche doivent être comprises entre 1 et 600 mois."
                )
            cleaned[key] = result
        for low, high in (("min_amount", "max_amount"), ("min_months", "max_months")):
            if (
                cleaned[low] is not None
                and cleaned[high] is not None
                and Decimal(cleaned[low]) > Decimal(cleaned[high])
            ):
                raise ValidationError("Bornes de tranche inversées.")
        for key in RATE_FIELDS:
            cleaned[key] = number(
                row.get(key), maximum="999.999" if key == "interest_rate" else "100"
            )
            limits = tariff[key]
            if cleaned[key] is not None and any(
                limits[bound] is not None
                and (
                    Decimal(cleaned[key]) < Decimal(limits[bound])
                    if bound == "min"
                    else Decimal(cleaned[key]) > Decimal(limits[bound])
                )
                for bound in ("min", "max")
            ):
                raise ValidationError(
                    "Un taux de tranche est hors des bornes du barème."
                )
        for other in bands:
            overlap = all(
                max(
                    Decimal(cleaned[low] if cleaned[low] is not None else 0),
                    Decimal(other[low] if other[low] is not None else 0),
                )
                <= min(
                    Decimal(cleaned[high] if cleaned[high] is not None else "1e30"),
                    Decimal(other[high] if other[high] is not None else "1e30"),
                )
                for low, high in (
                    ("min_amount", "max_amount"),
                    ("min_months", "max_months"),
                )
            )
            if overlap:
                raise ValidationError(
                    "Deux tranches tarifaires se chevauchent en montant et durée (bornes inclusives)."
                )
        bands.append(cleaned)
    tariff["bands"] = bands
    charges, identifiers = [], set()
    for row in tariff["charges"]:
        if not isinstance(row, dict) or set(row) - {
            "code",
            "label",
            "mode",
            "value",
            "min_amount",
            "max_amount",
            "tax_rate",
        }:
            raise ValidationError("Frais du barème invalides.")
        code, label, mode = row.get("code"), row.get("label"), row.get("mode")
        if (
            not isinstance(code, str)
            or not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", code)
            or code in identifiers
            or code.upper() == "PROCESSING"
            or code.upper().startswith("MANUAL_")
        ):
            raise ValidationError("Chaque frais doit avoir un code court et unique.")
        if (
            not isinstance(label, str)
            or not label.strip()
            or len(label) > 150
            or not isinstance(mode, str)
            or mode not in {"PERCENT", "AMOUNT"}
        ):
            raise ValidationError("Libellé ou mode de frais invalide.")
        identifiers.add(code)
        cleaned = {
            "code": code,
            "label": label.strip(),
            "mode": mode,
            "value": number(
                row.get("value"),
                maximum="100" if mode == "PERCENT" else "9999999999999999.99",
                places=3 if mode == "PERCENT" else 2,
                nullable=False,
            ),
            "tax_rate": number(row.get("tax_rate", "0"), maximum="100", nullable=False),
        }
        for key in ("min_amount", "max_amount"):
            cleaned[key] = number(row.get(key), maximum="9999999999999999.99", places=2)
        if (
            cleaned["min_amount"] is not None
            and cleaned["max_amount"] is not None
            and Decimal(cleaned["min_amount"]) > Decimal(cleaned["max_amount"])
        ):
            raise ValidationError("Le minimum de frais dépasse son plafond.")
        charges.append(cleaned)
    tariff["charges"] = charges
    return {"tariff": tariff}
