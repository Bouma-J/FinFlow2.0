import mimetypes
import os
from django.core.exceptions import ValidationError as DjangoValidationError

from django.http import FileResponse, HttpResponse
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError, PermissionDenied

from apps.common.access import apply_data_scope
from apps.common.permissions import HasModelPermission, MustChangePasswordGate
from apps.common.storage_urls import (
    CLIENT_FILE_FIELDS,
    image_content_type,
    verify_client_file_token,
)
from apps.common.tenancy import get_current_tenant_id
from apps.common.viewsets import AgencyScopedMixin, AgencyScopedViewSet

from .cbs_services import import_client_from_cbs, preview_client_from_cbs
from .models import Client
from .serializers import ClientListSerializer, ClientSerializer

FILE_FIELD_LABELS = {
    "photo": "photo du client",
    "id_document_scan": "scan de la pièce d'identité",
    "ifu_scan": "scan IFU",
    "rccm_scan": "scan RCCM",
    "manager_id_document_scan": "scan de la pièce du gérant",
}


def _unavailable_file_response(message: str, *, status: int = 404) -> HttpResponse:
    """Page HTML claire à la place du XML MinIO AccessDenied."""
    safe = (
        (message or "Document introuvable.")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
    html = f"""<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Document indisponible</title>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 0; padding: 2.5rem;
           background: #f4f6f5; color: #1c2b26; }}
    .box {{ max-width: 32rem; margin: 10vh auto; background: #fff;
            border: 1px solid #d7e0db; border-radius: 12px; padding: 1.5rem 1.75rem;
            box-shadow: 0 8px 24px rgba(28,43,38,.06); }}
    h1 {{ font-size: 1.15rem; margin: 0 0 .75rem; }}
    p {{ margin: 0; line-height: 1.5; color: #3d524a; }}
  </style>
</head>
<body>
  <div class="box">
    <h1>Document indisponible</h1>
    <p>{safe}</p>
  </div>
</body>
</html>"""
    return HttpResponse(html, status=status, content_type="text/html; charset=utf-8")


class ClientViewSet(AgencyScopedViewSet):
    """
    Consultation (liste / détail) : tous les clients de la filiale.
    Écriture : reste limitée au périmètre data_scope (agence / propre).
    """

    queryset = Client.objects.select_related("agency").all()
    serializer_class = ClientSerializer
    enforce_model_permissions = True
    action_perms = {
        # Accès fichier : JWT + view_client, ou jeton signé court (?token=).
        "photo": ["clients.view_client"],
        "files": ["clients.view_client"],
        "cbs_preview": ["clients.add_client"],
        "cbs_import": ["clients.add_client"],
        "form_configuration": ["clients.view_client"],
    }
    filterset_fields = ["client_type", "kyc_status", "agency", "is_active", "city"]
    search_fields = [
        "reference", "first_name", "last_name", "company_name",
        "national_id", "rccm", "ifu", "phone", "email",
        "manager_last_name", "manager_first_name",
        "cbs_client_id", "cbs_account_number",
    ]
    ordering_fields = ["created_at", "last_name", "company_name"]

    @action(detail=False, methods=["get"], url_path="form-configuration")
    def form_configuration(self, request):
        from apps.common.access import user_has_agency_access
        from apps.configuration.services import resolve_context
        from apps.tenants.models import Agency
        tenant_id = get_current_tenant_id()
        if not tenant_id:
            raise ValidationError("Sélectionnez une filiale.")
        if request.query_params.get("application"):
            from .compliance import dossier_configuration
            return Response(dossier_configuration(request, request.query_params.get("client"), request.query_params["application"]))
        client_type = request.query_params.get("client_type", "INDIVIDUAL")
        if client_type not in Client.ClientType.values:
            raise ValidationError("Type de client invalide.")
        agency_id = request.query_params.get("agency") or getattr(request.user, "agency_id", None)
        if agency_id:
            try:
                valid = Agency.objects.filter(pk=agency_id, tenant_id=tenant_id).exists()
            except (ValueError, DjangoValidationError):
                valid = False
            if not valid or not user_has_agency_access(request.user, agency_id):
                raise PermissionDenied("Agence hors de votre périmètre.")
        return Response(resolve_context(tenant_id, {"product": "", "agency": str(agency_id or ""),
                                                    "client_type": client_type, "individual_profile": ""}, resolve_conventions=False))

    # Consultation ouverte à toute la filiale (si droit view_client).
    TENANT_READ_ACTIONS = frozenset({"list", "retrieve", "photo", "files"})

    def get_permissions(self):
        if self.action in ("photo", "files"):
            # Jeton signé (URLs <img>) : pas de JWT ; sinon auth + droit view.
            token = (self.request.query_params.get("token") or "").strip()
            if token:
                return [AllowAny()]
            return [
                IsAuthenticated(),
                MustChangePasswordGate(),
                HasModelPermission(),
            ]
        return super().get_permissions()

    def get_serializer_class(self):
        if self.action == "list":
            return ClientListSerializer
        return ClientSerializer

    def get_queryset(self):
        # TenantContextMixin uniquement (pas le filtre agence/propre).
        qs = super(AgencyScopedMixin, self).get_queryset()
        if self.action != "list":
            qs = qs.prefetch_related("phones")
        if getattr(self, "action", None) in self.TENANT_READ_ACTIONS:
            return qs
        user = self.request.user
        if user and user.is_authenticated:
            qs = apply_data_scope(
                qs, user, self.agency_field, self.owner_field
            )
        return qs

    def _serve_client_file(self, pk, field: str):
        label = FILE_FIELD_LABELS.get(field, "document")
        if field not in CLIENT_FILE_FIELDS:
            return _unavailable_file_response(
                "Ce type de document n'est pas pris en charge.",
                status=400,
            )

        token = (self.request.query_params.get("token") or "").strip()
        user = getattr(self.request, "user", None)
        authenticated = bool(user and user.is_authenticated)

        if token:
            # Jeton lié à (client_id, field) — pas d'accès cross-tenant par UUID seul.
            if not verify_client_file_token(token, pk, field):
                return _unavailable_file_response(
                    "Lien expiré ou invalide. Rouvrez la fiche client.",
                    status=403,
                )
            client = Client.all_tenants.filter(pk=pk).first()
        elif authenticated:
            client = self.get_queryset().filter(pk=pk).first()
        else:
            return _unavailable_file_response(
                "Authentification requise pour accéder à ce document.",
                status=401,
            )

        if client is None:
            return _unavailable_file_response(
                "Client introuvable. Vérifiez le lien ou reconnectez-vous."
            )

        file_field = getattr(client, field, None)
        if not file_field or not getattr(file_field, "name", None):
            return _unavailable_file_response(
                f"Aucun fichier « {label} » n'est enregistré pour ce client."
            )

        try:
            handle = file_field.open("rb")
        except Exception:  # noqa: BLE001
            return _unavailable_file_response(
                f"Le fichier « {label} » est introuvable sur le serveur de "
                "stockage (accès refusé ou fichier manquant). "
                "Réimportez le document depuis la fiche client.",
                status=404,
            )

        filename = os.path.basename(file_field.name) or f"{field}.bin"
        if field == "photo":
            content_type = image_content_type(filename)
        else:
            content_type = (
                mimetypes.guess_type(filename)[0] or "application/octet-stream"
            )

        response = FileResponse(handle, content_type=content_type)
        response["Content-Disposition"] = f'inline; filename="{filename}"'
        response["Cache-Control"] = "private, max-age=300"
        return response

    @action(detail=True, methods=["get"], url_path="photo")
    def photo(self, request, pk=None):
        """Sert la photo du client pour affichage (<img> fiche client)."""
        return self._serve_client_file(pk, "photo")

    @action(
        detail=True,
        methods=["get"],
        url_path=r"files/(?P<field>[a-z_]+)",
    )
    def files(self, request, pk=None, field=None):
        """Sert un document client (scan pièce, IFU, RCCM…) via l'API."""
        return self._serve_client_file(pk, field or "")
    @action(detail=False, methods=["post"], url_path="cbs-preview")
    def cbs_preview(self, request):
        """Prévisualise un adhérent CBS (type physique / morale obligatoire)."""
        tenant_id = get_current_tenant_id()
        if tenant_id is None:
            return Response(
                {
                    "detail": (
                        "Aucune filiale sélectionnée. Choisissez une filiale "
                        "avant d'interroger le CBS."
                    )
                },
                status=400,
            )
        preview = preview_client_from_cbs(
            tenant_id=tenant_id, data=request.data or {}
        )
        # Ne pas renvoyer le raw volumineux à l'UI sauf besoin debug.
        payload = {k: v for k, v in preview.items() if k != "raw"}
        return Response(payload)

    @action(detail=False, methods=["post"], url_path="cbs-import")
    def cbs_import(self, request):
        """Crée un client à partir du CBS (type physique / morale déjà choisi)."""
        tenant_id = get_current_tenant_id()
        if tenant_id is None:
            return Response(
                {
                    "detail": (
                        "Aucune filiale sélectionnée. Choisissez une filiale "
                        "avant d'importer un client."
                    )
                },
                status=400,
            )
        client, preview = import_client_from_cbs(
            tenant_id=tenant_id,
            user=request.user,
            data=request.data or {},
        )
        data = ClientSerializer(client, context={"request": request}).data
        data["kyc_alert"] = bool(preview.get("kyc_alert"))
        data["cbs_est_valide"] = bool(preview.get("est_valide"))
        return Response(data, status=201)
