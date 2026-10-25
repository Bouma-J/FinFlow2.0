from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Max
from django.utils import timezone
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.catalog.models import CreditProduct
from apps.common.permissions import HasModelPermission, IsConfigurationAdministrator
from apps.common.access import apply_data_scope
from apps.common.tenancy import get_current_tenant_id
from apps.common.viewsets import TenantContextMixin
from apps.credits.models import CreditApplication
from apps.tenants.models import Agency, Tenant

from .catalog import parameter_catalog
from .models import ConfigurationProfile, ConfigurationPublicationLock
from .serializers import ConfigurationProfileSerializer
from .services import SECTIONS, active_profiles, application_configuration, context_for, matches, resolve_context, scope, specificity
from .rule_catalog import validate_rule_scope


class ConfigurationProfileViewSet(TenantContextMixin, mixins.ListModelMixin,
                                  mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = ConfigurationProfile.objects.select_related("product", "agency", "updated_by", "published_by")
    serializer_class = ConfigurationProfileSerializer
    permission_classes = [IsAuthenticated, IsConfigurationAdministrator, HasModelPermission]
    enforce_model_permissions = True
    action_perms = {
        "catalogue": ["configuration.view_configurationprofile"],
        "preview": ["configuration.preview_configurationprofile"],
        "publish": ["configuration.publish_configurationprofile"],
        "retire": ["configuration.publish_configurationprofile"],
        "submit": ["configuration.change_configurationprofile"],
        "reopen": ["configuration.change_configurationprofile"],
        "revise": ["configuration.add_configurationprofile"],
    }

    def tenant_id(self):
        tenant_id = get_current_tenant_id()
        if self.request.query_params.get("scope") == "group" or not tenant_id:
            if not getattr(self.request.user, "is_group_level", False):
                raise PermissionDenied("Le socle Groupe est réservé aux utilisateurs Groupe habilités.")
            return None
        if not tenant_id:
            raise ValidationError("Sélectionnez une filiale pour gérer sa configuration.")
        return tenant_id

    def get_queryset(self):
        return ConfigurationProfile.all_tenants.select_related("product", "agency", "updated_by", "published_by").filter(tenant_id=self.tenant_id())

    def get_serializer_context(self):
        return super().get_serializer_context() | {"tenant_id": self.tenant_id()}

    def _lock(self):
        ConfigurationPublicationLock.objects.get_or_create(pk=1)
        ConfigurationPublicationLock.objects.select_for_update().get(pk=1)
        if self.tenant_id():
            Tenant.objects.select_for_update().get(pk=self.tenant_id())

    def _locked_object(self):
        visible = self.get_object()
        return ConfigurationProfile.all_tenants.select_for_update().get(pk=visible.pk, tenant_id=self.tenant_id())

    @transaction.atomic
    def create(self, request):
        self._lock()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        code = serializer.validated_data["code"]
        if ConfigurationProfile.all_tenants.filter(tenant_id=self.tenant_id(), code=code).exists():
            raise ValidationError({"code": "Ce code existe. Créez une nouvelle version depuis le profil existant."})
        obj = serializer.save(tenant_id=self.tenant_id(), created_by=request.user, updated_by=request.user)
        return Response(self.get_serializer(obj).data, status=201)

    @transaction.atomic
    def partial_update(self, request, pk=None):
        self._lock()
        obj = self._locked_object()
        if obj.status != "DRAFT":
            raise ValidationError("Seul un brouillon peut être modifié. Créez une nouvelle version.")
        if request.data.get("expected_updated_at") != obj.updated_at.isoformat():
            # Le client DRF peut sérialiser UTC avec Z.
            from django.utils.dateparse import parse_datetime
            try:
                same = parse_datetime(request.data.get("expected_updated_at", "")) == obj.updated_at
            except (ValueError, TypeError):
                same = False
            if not same:
                raise ValidationError("Le brouillon a changé. Rechargez-le avant d'enregistrer.")
        data = {key: value for key, value in request.data.items() if key != "expected_updated_at"}
        if "code" in data and data["code"] != obj.code:
            raise ValidationError({"code": "Le code d'une série de versions ne peut pas changer."})
        serializer = self.get_serializer(obj, data=data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save(updated_by=request.user)
        return Response(serializer.data)

    @action(detail=False, methods=["get"])
    def catalogue(self, request):
        self.tenant_id()
        return Response(parameter_catalog())

    @transaction.atomic
    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        self._lock()
        obj = self._locked_object()
        if obj.status != "DRAFT" or not obj.reason.strip():
            raise ValidationError("Un brouillon et un motif de modification sont requis.")
        obj.status, obj.submitted_at = "REVIEW", timezone.now()
        obj.save(update_fields=["status", "submitted_at", "updated_at"])
        return Response(self.get_serializer(obj).data)

    @transaction.atomic
    @action(detail=True, methods=["post"])
    def reopen(self, request, pk=None):
        self._lock()
        obj = self._locked_object()
        if obj.status != "REVIEW":
            raise ValidationError("Ce profil n'est pas en attente de validation.")
        obj.status, obj.submitted_at = "DRAFT", None
        obj.save(update_fields=["status", "submitted_at", "updated_at"])
        return Response(self.get_serializer(obj).data)

    @transaction.atomic
    @action(detail=True, methods=["post"])
    def publish(self, request, pk=None):
        self._lock()
        obj = self._locked_object()
        if obj.status != "REVIEW":
            raise ValidationError("Soumettez d'abord le brouillon à validation.")
        if request.user.pk in {obj.created_by_id, obj.updated_by_id}:
            raise PermissionDenied("La publication doit être effectuée par un autre utilisateur habilité que l'auteur et le dernier rédacteur.")
        # Revalider au moment de publier, même si le catalogue a évolué.
        obj.overrides = self.get_serializer(obj).validate_overrides(obj.overrides)
        from .governance import validate_locks
        obj.locked_keys = validate_locks(obj.locked_keys, obj.overrides, group=obj.tenant_id is None)
        if obj.tenant_id is not None:
            group_profiles = active_profiles(None, at=obj.effective_from or timezone.now())
            # Inclure les socles déjà programmés : une publication locale ne doit
            # pas préparer sciemment une substitution qui deviendra neutralisée.
            group_profiles += list(ConfigurationProfile.all_tenants.filter(
                tenant__isnull=True, status="PUBLISHED", effective_from__gt=timezone.now()))
            for group_profile in group_profiles:
                overlaps = all(not left or not right or left == right for left, right in zip(scope(obj), scope(group_profile)))
                attempted = {f"{section}.{key}" for section, values in obj.overrides.items() for key in values}
                if overlaps and attempted.intersection(group_profile.locked_keys):
                    raise ValidationError("Ce profil adapte des clés verrouillées par le Groupe. Supprimez ces adaptations et simulez à nouveau.")
        try:
            validate_rule_scope(obj)
            from .simulation_catalog import resolve_simulation
            if obj.overrides.get("simulation"):
                resolve_simulation(obj.tenant_id, obj.overrides["simulation"])
            tariff = obj.overrides.get("pricing", {}).get("tariff", {})
            if tariff.get("engine") == "CONFIGURED" and obj.product_id and tariff["currency"] != obj.product.currency:
                raise DjangoValidationError("La devise du barème doit correspondre à celle du produit ciblé.")
        except DjangoValidationError as exc:
            raise ValidationError(exc.messages) from exc
        now = timezone.now()
        if obj.effective_from and obj.effective_from < now:
            raise ValidationError("La date d'application ne peut pas être passée. Videz-la pour une application immédiate.")
        others = ConfigurationProfile.all_tenants.filter(tenant_id=obj.tenant_id, status__in=["PUBLISHED", "RETIRED"])
        latest = {}
        for other in others.order_by("code", "-version"):
            latest.setdefault(other.code, other)
        occupied = active_profiles(obj.tenant_id) + [other for other in latest.values() if other.status == "PUBLISHED"]
        for other in occupied:
            if other.code != obj.code and scope(other) == scope(obj):
                raise ValidationError(f"Périmètre ambigu avec {other.code}. Révisez ce profil ou retirez-le.")
        for other in others:
            if other.code == obj.code and scope(other) != scope(obj):
                raise ValidationError("Conservez le périmètre de la série ; utilisez un nouveau code pour changer de périmètre.")
            if other.code == obj.code and other.version >= obj.version:
                raise ValidationError("Une version plus récente a déjà été publiée.")
            if other.code == obj.code and other.effective_from and other.effective_from > (obj.effective_from or now):
                raise ValidationError("Une version antérieure est programmée après cette date. Révisez le calendrier de publication.")
        obj.status, obj.published_at, obj.published_by = "PUBLISHED", now, request.user
        obj.effective_from = obj.effective_from or now
        obj.save()
        return Response(self.get_serializer(obj).data)

    @transaction.atomic
    @action(detail=True, methods=["post"])
    def retire(self, request, pk=None):
        self._lock()
        obj = self._locked_object()
        reason = request.data.get("reason", "")
        if obj.status != "PUBLISHED" or not isinstance(reason, str) or not reason.strip():
            raise ValidationError("Un profil publié et un motif de retrait sont requis.")
        obj.status, obj.retired_at, obj.retired_by = "RETIRED", timezone.now(), request.user
        obj.retirement_reason = reason.strip()
        obj.save(update_fields=["status", "retired_at", "retired_by", "retirement_reason", "updated_at"])
        return Response(self.get_serializer(obj).data)

    @transaction.atomic
    @action(detail=True, methods=["post"])
    def revise(self, request, pk=None):
        self._lock()
        original = self._locked_object()
        series = ConfigurationProfile.all_tenants.filter(tenant_id=original.tenant_id, code=original.code)
        if series.filter(status__in=["DRAFT", "REVIEW"]).exists():
            raise ValidationError("Cette série possède déjà un brouillon ou une version à valider.")
        version = (series.aggregate(value=Max("version"))["value"] or 0) + 1
        obj = ConfigurationProfile.all_tenants.create(
            tenant_id=original.tenant_id, code=original.code, name=original.name, version=version,
            product_id=original.product_id, agency_id=original.agency_id,
            client_type=original.client_type, individual_profile=original.individual_profile,
            overrides=original.overrides, locked_keys=original.locked_keys, created_by=request.user, updated_by=request.user,
        )
        return Response(self.get_serializer(obj).data, status=201)

    @action(detail=True, methods=["post"])
    def preview(self, request, pk=None):
        obj = self.get_object()
        target_tenant = get_current_tenant_id() if obj.tenant_id is None else self.tenant_id()
        dossier = None
        application_id = request.data.get("application")
        if application_id:
            if not request.user.has_perm("credits.view_creditapplication"):
                raise PermissionDenied("La simulation sur dossier nécessite le droit de consulter les crédits.")
            if not isinstance(application_id, str):
                raise ValidationError("Dossier de simulation invalide.")
            try:
                dossier = apply_data_scope(
                    CreditApplication.all_tenants.filter(tenant_id=target_tenant).select_related("client", "product"),
                    request.user, agency_field="agency", owner_field="created_by",
                ).filter(pk=application_id).first()
            except (ValueError, DjangoValidationError):
                dossier = None
            if dossier is None:
                raise ValidationError("Dossier introuvable dans votre périmètre.")
        context = {key: request.data.get(key, "") or "" for key in ("product", "agency", "client_type", "individual_profile")}
        if dossier is not None:
            context = context_for(dossier)
        if any(not isinstance(value, str) for value in context.values()):
            raise ValidationError("Les critères de simulation doivent être des chaînes.")
        if (context["client_type"] not in {"", "INDIVIDUAL", "CORPORATE", "PROFESSIONAL"}
                or context["individual_profile"] not in {"", "SALARIE", "INDEPENDANT", "MIXTE"}
                or (context["individual_profile"] and context["client_type"] != "INDIVIDUAL")):
            raise ValidationError("Profil de clientèle invalide pour la simulation.")
        for key, model in (("product", CreditProduct), ("agency", Agency)):
            if context[key]:
                try:
                    valid = model.all_tenants.filter(pk=context[key], tenant_id=target_tenant).exists()
                except (ValueError, DjangoValidationError):
                    valid = False
                if not valid:
                    raise ValidationError({key: "Référence introuvable dans cette filiale."})
        before = application_configuration(dossier) if dossier is not None else resolve_context(target_tenant, context)
        after = resolve_context(target_tenant, context, candidate=obj)
        changes = [{"section": section, "key": key, "before": before[section].get(key), "after": value}
                   for section in SECTIONS
                   for key, value in after[section].items() if value != before[section].get(key)]
        dossiers = apply_data_scope(CreditApplication.all_tenants.filter(tenant_id=target_tenant),
                                    request.user, agency_field="agency", owner_field="created_by")
        if not request.user.has_perm("credits.view_creditapplication"):
            dossiers = dossiers.none()
        for field, value in (("product_id", obj.product_id), ("agency_id", obj.agency_id), ("client__client_type", obj.client_type)):
            if value:
                dossiers = dossiers.filter(**{field: value})
        if obj.individual_profile:
            dossiers = dossiers.filter(financial_analyses__is_reference=True,
                                       financial_analyses__individual_profile=obj.individual_profile)
        impact = {
            "editable_matching": dossiers.filter(status__in=["DRAFT", "RETURNED"], configuration_snapshot={}).distinct().count(),
            "frozen_matching": dossiers.exclude(configuration_snapshot={}).distinct().count(),
            "note": "Les règles conservées des dossiers soumis ne sont pas remplacées. L'organisation de la transmission CBS reste courante.",
        }
        result = {"matches": matches(obj, context), "specificity": specificity(obj),
                  "before": before, "after": after, "changes": changes, "impact": impact}
        if dossier is not None:
            from apps.credits.eligibility import assess_rules
            from apps.credits.pricing import quote_pricing

            result["evaluation"] = {"reference": dossier.reference,
                                    "before": assess_rules(dossier, configuration=before),
                                    "after": assess_rules(dossier, configuration=after),
                                    "note": "Simulation sans enregistrement. Les règles conservées de ce dossier restent inchangées."}
            result["pricing_evaluation"] = {"before": quote_pricing(dossier, configuration=before), "after": quote_pricing(dossier, configuration=after)}
        return Response(result)
