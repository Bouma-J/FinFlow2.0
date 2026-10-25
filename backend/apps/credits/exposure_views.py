"""Situations documentées : saisie, vérification indépendante et révocation."""
from decimal import Decimal
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from apps.clients.models import Client
from apps.common.access import apply_data_scope
from apps.common.tenancy import get_current_tenant_id
from apps.common.viewsets import TenantScopedViewSet
from .exposure_models import BorrowerGroup, CreditExposureObservation
from .models import CreditApplication


def client_visible(client, request):
    return apply_data_scope(Client.all_tenants.filter(pk=client.pk, tenant_id=get_current_tenant_id()), request.user).exists()


class BorrowerGroupSerializer(serializers.ModelSerializer):
    clients = serializers.PrimaryKeyRelatedField(queryset=Client.all_tenants.all(), many=True)
    clients_detail = serializers.SerializerMethodField()

    def get_clients_detail(self, obj):
        return [{"id": str(client.pk), "name": client.display_name} for client in obj.clients.order_by("pk")]

    class Meta:
        model = BorrowerGroup
        fields = ["id", "code", "name", "reason", "clients", "clients_detail", "is_active", "updated_at"]
        read_only_fields = ["id", "updated_at"]

    def validate(self, attrs):
        members = attrs.get("clients", list(self.instance.clients.all()) if self.instance else [])
        if not 2 <= len({client.pk for client in members}) <= 100:
            raise ValidationError({"clients": "Un groupe doit comprendre entre 2 et 100 clients distincts."})
        if any(not client_visible(client, self.context["request"]) for client in members):
            raise ValidationError({"clients": "Tous les clients doivent appartenir à votre périmètre et à la filiale active."})
        if not attrs.get("reason", getattr(self.instance, "reason", "")).strip():
            raise ValidationError({"reason": "Justifiez le lien économique ou la solidarité."})
        return attrs


class BorrowerGroupViewSet(TenantScopedViewSet):
    queryset = BorrowerGroup.objects.all()
    serializer_class = BorrowerGroupSerializer
    http_method_names = ["get", "post", "patch", "head", "options"]
    filterset_fields = ["clients", "is_active"]
    search_fields = ["code", "name"]

    def get_queryset(self):
        qs = super().get_queryset()
        visible_ids = apply_data_scope(Client.all_tenants.filter(tenant_id=get_current_tenant_id()), self.request.user).values_list("pk", flat=True)
        # La permission de groupe ne donne pas accès aux identités d'autres agences.
        return qs.exclude(clients__in=Client.all_tenants.filter(tenant_id=get_current_tenant_id()).exclude(pk__in=visible_ids)).distinct()


class CreditExposureObservationSerializer(serializers.ModelSerializer):
    class Meta:
        model = CreditExposureObservation
        fields = ["id", "client", "currency", "as_of", "drawn_principal", "undrawn_commitments", "guarantees_given",
                  "source_reference", "evidence", "completeness_confirmed", "note", "status", "verified_by", "verified_at", "revocation_reason", "created_by", "updated_by", "updated_at"]
        read_only_fields = ["id", "status", "verified_by", "verified_at", "revocation_reason", "created_by", "updated_by", "updated_at"]

    def validate(self, attrs):
        def current(key):
            return attrs.get(key, getattr(self.instance, key, None))
        if self.instance and self.instance.status != "DRAFT":
            raise ValidationError("Une situation vérifiée ou révoquée est conservée. Créez une nouvelle situation.")
        client = current("client")
        if not client or not client_visible(client, self.context["request"]):
            raise ValidationError({"client": "Client hors de votre périmètre."})
        if self.instance and client.pk != self.instance.client_id:
            raise ValidationError({"client": "Une situation ne peut être réaffectée à un autre client."})
        currency = current("currency") or ""
        if len(currency) != 3 or not currency.isascii() or not currency.isalpha() or not currency.isupper():
            raise ValidationError({"currency": "Trois lettres majuscules sont attendues."})
        if current("as_of") > timezone.localdate():
            raise ValidationError({"as_of": "La date de situation ne peut être future."})
        for key in ("drawn_principal", "undrawn_commitments", "guarantees_given"):
            if current(key) is not None and current(key) < Decimal("0"):
                raise ValidationError({key: "Le montant doit être positif ou nul."})
        evidence = current("evidence")
        if not evidence or evidence.tenant_id != client.tenant_id or evidence.is_deleted or not evidence.file:
            raise ValidationError({"evidence": "Un justificatif GED réel de cette filiale est requis."})
        client_type = ContentType.objects.get_for_model(Client)
        application_type = ContentType.objects.get_for_model(CreditApplication)
        allowed = evidence.content_type_id == client_type.pk and str(evidence.object_id) == str(client.pk)
        if evidence.content_type_id == application_type.pk:
            allowed = apply_data_scope(CreditApplication.all_tenants.filter(pk=evidence.object_id, tenant_id=client.tenant_id, client=client), self.context["request"].user).exists()
        if not allowed:
            raise ValidationError({"evidence": "Le justificatif doit être rattaché au client ou à l'un de ses dossiers accessibles."})
        if not current("source_reference") or not current("source_reference").strip():
            raise ValidationError({"source_reference": "La source et sa référence sont obligatoires."})
        return attrs


class CreditExposureObservationViewSet(TenantScopedViewSet):
    queryset = CreditExposureObservation.objects.select_related("client", "evidence").all()
    serializer_class = CreditExposureObservationSerializer
    http_method_names = ["get", "post", "patch", "head", "options"]
    filterset_fields = ["client", "currency", "status"]
    action_perms = {"verify": ["credits.verify_creditexposureobservation"], "revoke": ["credits.verify_creditexposureobservation"]}

    def get_queryset(self):
        qs = super().get_queryset()
        clients = apply_data_scope(Client.all_tenants.filter(tenant_id=get_current_tenant_id()), self.request.user)
        return qs.filter(client__in=clients)

    @transaction.atomic
    def partial_update(self, request, *args, **kwargs):
        visible = self.get_object()
        CreditExposureObservation.all_tenants.select_for_update().get(pk=visible.pk)
        return super().partial_update(request, *args, **kwargs)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def verify(self, request, pk=None):
        from .exposure import evidence_matches_client
        visible = self.get_object()
        obj = CreditExposureObservation.all_tenants.select_for_update().get(pk=visible.pk)
        if obj.status != "DRAFT":
            raise ValidationError("Cette situation n'est plus un brouillon.")
        if request.user.pk in {obj.created_by_id, obj.updated_by_id}:
            raise PermissionDenied("Le vérificateur doit être distinct de l'auteur et du dernier rédacteur.")
        if not obj.completeness_confirmed:
            raise ValidationError("Confirmez que la situation couvre tous les engagements externes, y compris le CBS, à sa date.")
        if not evidence_matches_client(obj) or obj.evidence.verification_status != "VERIFIED" or obj.evidence.is_deleted or not obj.evidence.file or (obj.evidence.expiry_date and obj.evidence.expiry_date < timezone.localdate()):
            raise ValidationError("Le justificatif doit être vérifié et non expiré.")
        obj.status, obj.verified_by, obj.verified_at = "VERIFIED", request.user, timezone.now()
        obj.save(update_fields=["status", "verified_by", "verified_at", "updated_at"])
        return Response(self.get_serializer(obj).data)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def revoke(self, request, pk=None):
        visible = self.get_object()
        obj = CreditExposureObservation.all_tenants.select_for_update().get(pk=visible.pk)
        reason = request.data.get("reason", "")
        if obj.status != "VERIFIED" or not isinstance(reason, str) or not reason.strip():
            raise ValidationError("Une situation vérifiée et un motif de révocation sont requis.")
        obj.status, obj.revocation_reason = "REVOKED", reason.strip()
        obj.updated_by = request.user
        obj.save(update_fields=["status", "revocation_reason", "updated_by", "updated_at"])
        return Response(self.get_serializer(obj).data)
