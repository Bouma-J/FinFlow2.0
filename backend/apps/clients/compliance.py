"""Exigences KYC internes configurées ; aucune valeur réglementaire implicite."""
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.configuration.forms_catalog import document_fields, native_kyc_fields, validate_custom_values
from apps.configuration.services import application_configuration, resolve_context, plain


def client_configuration(client):
    return resolve_context(client.tenant_id, {"product": "", "agency": str(client.agency_id or ""),
                                           "client_type": client.client_type, "individual_profile": ""}, resolve_conventions=False)


def dossier_configuration(request, client_id, application_id):
    from rest_framework.exceptions import PermissionDenied, ValidationError as ApiValidationError
    from apps.common.access import apply_data_scope
    from apps.common.tenancy import get_current_tenant_id
    from apps.credits.models import CreditApplication
    if not client_id or not request or not request.user.has_perm("credits.view_creditapplication"):
        raise PermissionDenied("Le contexte dossier nécessite un client existant et le droit de consulter les crédits.")
    try:
        application = apply_data_scope(CreditApplication.all_tenants.filter(
            tenant_id=get_current_tenant_id(), client_id=client_id), request.user,
            agency_field="agency", owner_field="created_by").filter(pk=application_id).first()
    except (ValueError, ValidationError):
        application = None
    if application is None:
        raise ApiValidationError("Dossier introuvable dans le périmètre de ce client.")
    return application_configuration(application)


def kyc_failures(client, configuration=None, application=None, at=None):
    config = configuration or (application_configuration(application) if application is not None else client_configuration(client))
    rules, failures, today = config["kyc"], [], at or timezone.localdate()
    for key in rules["required_fields"]:
        value = getattr(client, key, None)
        if value is None or isinstance(value, str) and not value.strip():
            failures.append(f"KYC : {native_kyc_fields().get(key, key)} est requis.")
    for key in rules["required_documents"]:
        if not getattr(client, key, None):
            failures.append(f"KYC : {document_fields().get(key, key)} est requis.")
    if rules["check_expiry"]:
        key = "manager_id_document_expiry_date" if client.client_type in {"CORPORATE", "PROFESSIONAL"} else "id_document_expiry_date"
        expiry = getattr(client, key, None)
        if not expiry or expiry < today:
            failures.append("KYC : la date d'expiration de la pièce doit être renseignée et non échue.")
    validated = getattr(client, "kyc_validated_at", None)
    if rules["validity_days"] and (not validated or validated + timedelta(days=rules["validity_days"]) < today):
        failures.append("KYC : la durée de validité de la revue est dépassée ou sa date est absente.")
    try:
        validate_custom_values(config["forms"]["client_fields"], getattr(client, "custom_fields", {}) or {}, require=True)
    except ValidationError as exc:
        failures.extend(exc.messages)
    return failures


def kyc_evidence(client, configuration):
    """Données et références de fichiers qui justifient la revue applicable."""
    rules = configuration["kyc"]
    return plain({
        "status": client.kyc_status, "validated_at": client.kyc_validated_at,
        "required_fields": {key: getattr(client, key, None) for key in rules["required_fields"]},
        "required_documents": {key: getattr(getattr(client, key, None), "name", "") for key in rules["required_documents"]},
        "identity_expiry": {key: getattr(client, key, None) for key in ("id_document_expiry_date", "manager_id_document_expiry_date")} if rules["check_expiry"] else {},
        "custom_fields": client.custom_fields,
    })


def cbs_reference_value(configuration, key, value):
    """Correspondance explicitement configurée pour l'import, sans deviner de code CBS."""
    return next((entry["code"] for entry in configuration["references"][key]
                 if entry["active"] and entry["cbs_code"] and entry["cbs_code"] == str(value)), None)
