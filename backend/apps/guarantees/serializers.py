import json

from django.core.exceptions import ObjectDoesNotExist
from rest_framework import serializers

from apps.common.storage_urls import file_download_url, presign_file_fields

from .models import (
    Guarantee,
    PledgeCategory,
    GuaranteeDocument,
    GuaranteeFormalizationRequest,
    GuaranteeJewelryItem,
    GuaranteeMovement,
    GuaranteePhoto,
    GuaranteeReleaseRequest,
    ReleaseFee,
    DationAsset,
    DationFee,
    DationRequest,
    FormalizationFee,
)

_OPEN_DATION_STATUSES = (
    DationRequest.Status.DRAFT,
    DationRequest.Status.IN_APPROVAL,
    DationRequest.Status.RETURNED,
    DationRequest.Status.APPROVED,
    DationRequest.Status.BLOCKED,
)
_OPEN_RELEASE_STATUSES = (
    GuaranteeReleaseRequest.Status.DRAFT,
    GuaranteeReleaseRequest.Status.IN_APPROVAL,
    GuaranteeReleaseRequest.Status.RETURNED,
    GuaranteeReleaseRequest.Status.APPROVED,
    GuaranteeReleaseRequest.Status.BLOCKED,
)
_OPEN_FORMALIZATION_STATUSES = (
    GuaranteeFormalizationRequest.Status.DRAFT,
    GuaranteeFormalizationRequest.Status.IN_PROGRESS,
    GuaranteeFormalizationRequest.Status.IN_APPROVAL,
    GuaranteeFormalizationRequest.Status.RETURNED,
    GuaranteeFormalizationRequest.Status.APPROVED,
)


def _open_dation_id(guarantee) -> str | None:
    link = (
        guarantee.dation_asset_links.filter(
            dation__status__in=_OPEN_DATION_STATUSES
        )
        .order_by("-created_at")
        .only("dation_id")
        .first()
    )
    return str(link.dation_id) if link else None


def _open_release_id(guarantee) -> str | None:
    req = (
        guarantee.release_requests.filter(status__in=_OPEN_RELEASE_STATUSES)
        .order_by("-created_at")
        .only("id")
        .first()
    )
    return str(req.id) if req else None


def _open_formalization_id(guarantee) -> str | None:
    req = (
        guarantee.formalization_requests.filter(
            status__in=_OPEN_FORMALIZATION_STATUSES
        )
        .order_by("-created_at")
        .only("id")
        .first()
    )
    return str(req.id) if req else None


def _completed_dation_id(guarantee) -> str | None:
    """Dation qui a réalisé cette garantie (bien source)."""
    link = (
        guarantee.dation_asset_links.filter(
            dation__status=DationRequest.Status.COMPLETED
        )
        .order_by("-dation__completed_at", "-created_at")
        .only("dation_id")
        .first()
    )
    return str(link.dation_id) if link else None


def _origin_dation_id(guarantee) -> str | None:
    """Dation dont cette garantie est le bien issu (type DATION)."""
    origin = (
        guarantee.dation_origins.order_by("-completed_at", "-created_at")
        .only("id")
        .first()
    )
    return str(origin.id) if origin else None


class GuaranteeMovementSerializer(serializers.ModelSerializer):
    movement_type_display = serializers.CharField(
        source="get_movement_type_display", read_only=True
    )

    class Meta:
        model = GuaranteeMovement
        fields = [
            "id", "guarantee", "movement_type", "movement_type_display",
            "movement_date", "value", "target_application", "comment",
        ]
        read_only_fields = ["id", "movement_type_display"]

    def validate_movement_type(self, value):
        locked = {
            GuaranteeMovement.MovementType.RELEASE,
            GuaranteeMovement.MovementType.REALIZATION,
            GuaranteeMovement.MovementType.TRANSFER,
        }
        if value in locked:
            raise serializers.ValidationError(
                "Utilisez le processus métier (main levée, dation) "
                "plutôt qu'un mouvement direct."
            )
        return value


class GuaranteePhotoSerializer(serializers.ModelSerializer):
    class Meta:
        model = GuaranteePhoto
        fields = ["id", "image", "caption"]

    def to_representation(self, instance):
        return presign_file_fields(
            super().to_representation(instance), instance, "image"
        )


class GuaranteeDocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = GuaranteeDocument
        fields = ["id", "title", "file", "created_at"]
        read_only_fields = ["id", "created_at"]

    def to_representation(self, instance):
        return presign_file_fields(
            super().to_representation(instance), instance, "file"
        )


class GuaranteeJewelryItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = GuaranteeJewelryItem
        fields = ["id", "nature", "weight", "description"]
        read_only_fields = ["id"]


class JewelryItemsField(serializers.Field):
    """Accepte une liste de bijoux (JSON) transmise via multipart ou JSON."""

    def to_representation(self, value):
        return GuaranteeJewelryItemSerializer(value.all(), many=True).data

    def to_internal_value(self, data):
        if isinstance(data, str):
            data = data.strip()
            if not data:
                return []
            try:
                data = json.loads(data)
            except json.JSONDecodeError as exc:
                raise serializers.ValidationError(
                    "Format des bijoux invalide."
                ) from exc
        if not isinstance(data, list):
            raise serializers.ValidationError("Une liste de bijoux est attendue.")
        items = []
        for raw in data:
            if not isinstance(raw, dict):
                continue
            nature = str(raw.get("nature") or "").strip()
            desc = str(raw.get("description") or "").strip()
            weight_raw = raw.get("weight")
            if not (nature or desc or weight_raw not in (None, "")):
                continue
            weight = None
            if weight_raw not in (None, ""):
                try:
                    weight = float(weight_raw)
                except (TypeError, ValueError) as exc:
                    raise serializers.ValidationError(
                        f"Poids invalide pour « {nature or 'bijou'} »."
                    ) from exc
            items.append(
                {"nature": nature, "weight": weight, "description": desc}
            )
        return items


def _collection_link_for_application(application):
    """Pont dossier → prêt → recouvrement (None si pas encore mis en place)."""
    if application is None:
        return None, "", ""
    try:
        loan = application.loan
    except (ObjectDoesNotExist, AttributeError):
        return None, "", ""
    case = getattr(loan, "collection_case", None)
    if case is None:
        return None, "", ""
    return str(case.id), case.stage, case.get_stage_display()


class GuaranteeListSerializer(serializers.ModelSerializer):
    """Liste allégée — sans mouvements, photos ni scans."""

    type_display = serializers.CharField(
        source="get_guarantee_type_display", read_only=True
    )
    renewed_from_reference = serializers.CharField(
        source="renewed_from.reference", read_only=True, default=None
    )
    surety_display = serializers.SerializerMethodField()
    client_display = serializers.SerializerMethodField()
    application_reference = serializers.SerializerMethodField()
    collection_case_id = serializers.SerializerMethodField()
    collection_stage_display = serializers.SerializerMethodField()
    open_formalization_id = serializers.SerializerMethodField()
    open_dation_id = serializers.SerializerMethodField()
    open_release_id = serializers.SerializerMethodField()
    completed_dation_id = serializers.SerializerMethodField()
    origin_dation_id = serializers.SerializerMethodField()
    process_busy = serializers.SerializerMethodField()

    class Meta:
        model = Guarantee
        fields = [
            "id", "reference", "guarantee_type", "type_display", "agency",
            "pledge_category", "client", "client_display",
            "application", "application_reference",
            "belongs_to_applicant", "surety", "surety_display",
            "current_value", "ltv_ratio", "status",
            "registration_number", "registration_date",
            "registration_authority", "formalized_at",
            "open_formalization_id", "open_dation_id", "open_release_id",
            "completed_dation_id", "origin_dation_id", "process_busy",
            "collection_case_id", "collection_stage_display",
            "renewed_from_reference", "created_at",
        ]
        read_only_fields = fields

    def get_surety_display(self, obj) -> str | None:
        if not obj.surety_id:
            return None
        return getattr(obj.surety, "display_name", None) or str(obj.surety)

    def get_client_display(self, obj) -> str | None:
        if not obj.client_id:
            return None
        return getattr(obj.client, "display_name", None) or str(obj.client)

    def get_application_reference(self, obj) -> str | None:
        if not obj.application_id:
            return None
        return obj.application.reference or str(obj.application_id)

    def get_collection_case_id(self, obj):
        return _collection_link_for_application(obj.application)[0]

    def get_collection_stage_display(self, obj):
        return _collection_link_for_application(obj.application)[2]

    def get_open_formalization_id(self, obj):
        return _open_formalization_id(obj)

    def get_open_dation_id(self, obj):
        return _open_dation_id(obj)

    def get_open_release_id(self, obj):
        return _open_release_id(obj)

    def get_completed_dation_id(self, obj):
        return _completed_dation_id(obj)

    def get_origin_dation_id(self, obj):
        return _origin_dation_id(obj)

    def get_process_busy(self, obj):
        from .busy import guarantee_busy

        return guarantee_busy(obj)


class GuaranteeSerializer(serializers.ModelSerializer):
    movements = GuaranteeMovementSerializer(many=True, read_only=True)
    photos = GuaranteePhotoSerializer(many=True, read_only=True)
    documents = GuaranteeDocumentSerializer(many=True, read_only=True)
    jewelry_items = JewelryItemsField(required=False)
    type_display = serializers.CharField(
        source="get_guarantee_type_display", read_only=True
    )
    status_display = serializers.CharField(
        source="get_status_display", read_only=True
    )
    renewed_from_reference = serializers.CharField(
        source="renewed_from.reference", read_only=True, default=None
    )
    surety_display = serializers.SerializerMethodField()
    client_display = serializers.SerializerMethodField()
    application_reference = serializers.SerializerMethodField()
    collection_case_id = serializers.SerializerMethodField()
    collection_stage_display = serializers.SerializerMethodField()
    agency_name = serializers.SerializerMethodField()
    open_formalization_id = serializers.SerializerMethodField()
    open_dation_id = serializers.SerializerMethodField()
    open_release_id = serializers.SerializerMethodField()
    completed_dation_id = serializers.SerializerMethodField()
    origin_dation_id = serializers.SerializerMethodField()
    process_busy = serializers.SerializerMethodField()
    accept_existing = serializers.BooleanField(
        write_only=True, required=False, default=False
    )

    class Meta:
        model = Guarantee
        fields = [
            "id", "reference", "guarantee_type", "type_display", "agency",
            "agency_name",
            "pledge_category", "client", "client_display",
            "application", "application_reference",
            "collection_case_id", "collection_stage_display",
            "belongs_to_applicant", "surety", "surety_display",
            "description", "owners", "expertise_value", "current_value",
            "is_insured", "insurance_reference",
            # Propriétaire
            "owner_last_name", "owner_first_name", "owner_marital_status",
            "matrimonial_regime",
            # Hypothèque
            "document_type", "document_number", "document_issue_date",
            "document_validity_date",
            "address", "expertise_date", "expertise_firm", "expert_name",
            "expertise_reference",
            "value_to_consider",
            "ltv_ratio", "occupancy_status", "document_scan",
            "expertise_report_scan", "lease_contract_scan",
            "legal_situation_certificate_scan",
            # Gage — moyen roulant
            "chassis_number", "engine_number", "brand", "model_name",
            "registration", "power", "first_registration_year",
            "acquisition_date", "acquisition_value", "resale_value",
            "estimation_date", "registration_card_scan",
            "mechanical_expertise_scan", "technical_inspection_scan",
            "insurance_scan", "purchase_invoice_scan", "additional_info",
            # Gage — objet de valeur
            "raw_material_price", "expertise_certificate_scan",
            "origin_certificate_scan",
            # Garantie financière
            "financial_type", "account_number", "balance", "remuneration_rate",
            "deposit_maturity_date", "isin_code", "volatility_history",
            "security_discount", "pledge_deed_scan",
            # Suivi
            "status", "status_display", "last_valuation_date",
            "photos", "documents",
            "movements",
            "jewelry_items", "renewed_from", "renewed_from_reference",
            "registration_number", "registration_date",
            "registration_authority", "formalized_at",
            "open_formalization_id", "open_dation_id", "open_release_id",
            "completed_dation_id", "origin_dation_id", "process_busy",
            "accept_existing",
            "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "status", "status_display", "current_value", "ltv_ratio",
            "renewed_from", "renewed_from_reference", "surety_display",
            "client_display", "application_reference", "agency_name",
            "collection_case_id", "collection_stage_display",
            "registration_number", "registration_date",
            "registration_authority", "formalized_at",
            "open_formalization_id", "open_dation_id", "open_release_id",
            "completed_dation_id", "origin_dation_id", "process_busy",
            "created_at", "updated_at",
        ]

    def get_surety_display(self, obj) -> str | None:
        if not obj.surety_id:
            return None
        return getattr(obj.surety, "display_name", None) or str(obj.surety)

    def get_client_display(self, obj) -> str | None:
        if not obj.client_id:
            return None
        return getattr(obj.client, "display_name", None) or str(obj.client)

    def get_application_reference(self, obj) -> str | None:
        if not obj.application_id:
            return None
        return obj.application.reference or str(obj.application_id)

    def get_collection_case_id(self, obj):
        return _collection_link_for_application(obj.application)[0]

    def get_collection_stage_display(self, obj):
        return _collection_link_for_application(obj.application)[2]

    def get_agency_name(self, obj) -> str | None:
        if not obj.agency_id:
            return None
        return obj.agency.name

    def get_open_formalization_id(self, obj):
        return _open_formalization_id(obj)

    def get_open_dation_id(self, obj):
        return _open_dation_id(obj)

    def get_open_release_id(self, obj):
        return _open_release_id(obj)

    def get_completed_dation_id(self, obj):
        return _completed_dation_id(obj)

    def get_origin_dation_id(self, obj):
        return _origin_dation_id(obj)

    def get_process_busy(self, obj):
        from .busy import guarantee_busy

        return guarantee_busy(obj)

    def to_representation(self, instance):
        return presign_file_fields(
            super().to_representation(instance),
            instance,
            "document_scan",
            "expertise_report_scan",
            "lease_contract_scan",
            "legal_situation_certificate_scan",
            "registration_card_scan",
            "mechanical_expertise_scan",
            "technical_inspection_scan",
            "insurance_scan",
            "purchase_invoice_scan",
            "expertise_certificate_scan",
            "origin_certificate_scan",
            "pledge_deed_scan",
        )

    def validate(self, attrs):
        from apps.common.upload_validation import validate_attrs_uploads

        attrs = validate_attrs_uploads(attrs, self.context, check_quota=True)
        belongs = attrs.get(
            "belongs_to_applicant",
            getattr(self.instance, "belongs_to_applicant", True),
        )
        # multipart envoie souvent "true"/"false" déjà coercés en bool par DRF
        if isinstance(belongs, str):
            belongs = belongs.strip().lower() in ("1", "true", "yes", "oui")
            attrs["belongs_to_applicant"] = belongs

        surety = attrs.get(
            "surety",
            getattr(self.instance, "surety", None) if self.instance else None,
        )
        if "surety" in attrs and attrs["surety"] == "":
            surety = None
            attrs["surety"] = None

        if belongs:
            attrs["surety"] = None
        elif not surety:
            raise serializers.ValidationError({
                "surety": (
                    "Indiquez la caution : le bien n'appartient pas au "
                    "client demandeur."
                ),
            })

        client = attrs.get(
            "client",
            getattr(self.instance, "client", None) if self.instance else None,
        )
        application = attrs.get(
            "application",
            getattr(self.instance, "application", None) if self.instance else None,
        )
        if client and application and application.client_id != client.pk:
            raise serializers.ValidationError({
                "application": "Ce dossier n'appartient pas au client indiqué.",
            })

        def merged(name, default=None):
            if name in attrs:
                return attrs[name]
            if self.instance is not None:
                return getattr(self.instance, name, default)
            return default

        g_type = merged("guarantee_type")
        pledge_cat = merged("pledge_category") or ""
        errors = {}
        is_create = self.instance is None
        is_mortgage = g_type == Guarantee.GuaranteeType.MORTGAGE
        is_vehicle = (
            g_type == Guarantee.GuaranteeType.PLEDGE
            and pledge_cat == PledgeCategory.VEHICLE
        )

        if is_mortgage or is_vehicle:
            if not (merged("document_type") or "").strip():
                errors["document_type"] = (
                    "Indiquez le type de document pris en garantie."
                )
            if not (merged("document_number") or "").strip():
                errors["document_number"] = "Indiquez le numéro du document."
            if is_create and not merged("document_issue_date"):
                errors["document_issue_date"] = (
                    "Indiquez la date d'établissement du document."
                )
        if is_vehicle and not (merged("chassis_number") or "").strip():
            errors["chassis_number"] = (
                "Le numéro de châssis est obligatoire pour un gage véhicule."
            )
        if is_create and (is_mortgage or is_vehicle):
            expertise_value = merged("expertise_value")
            if expertise_value in (None, ""):
                errors["expertise_value"] = "Indiquez la valeur d'expertise."
            if not merged("expertise_date"):
                errors["expertise_date"] = "Indiquez la date de l'expertise."
            if not (
                (merged("expert_name") or "").strip()
                or (merged("expertise_firm") or "").strip()
            ):
                errors["expert_name"] = (
                    "Indiquez l'expert ou le cabinet d'expertise."
                )

        accept_existing = attrs.pop("accept_existing", False)
        if isinstance(accept_existing, str):
            accept_existing = accept_existing.strip().lower() in (
                "1", "true", "yes", "oui",
            )

        from .uniqueness import uniqueness_error

        if not accept_existing:
            conflict = uniqueness_error(
                guarantee_type=g_type,
                pledge_category=pledge_cat,
                document_type=merged("document_type") or "",
                document_number=merged("document_number") or "",
                chassis_number=merged("chassis_number") or "",
                exclude_id=getattr(self.instance, "pk", None),
                tenant_id=getattr(self.instance, "tenant_id", None),
            )
            if conflict:
                errors.update(conflict)
        if errors:
            raise serializers.ValidationError(errors)
        return attrs

    def _save_photos(self, guarantee):
        request = self.context.get("request")
        if not request:
            return
        from apps.common.upload_validation import validate_uploaded_file

        for image in request.FILES.getlist("photos"):
            validate_uploaded_file(image, tenant=guarantee.tenant, check_quota=True)
            GuaranteePhoto.objects.create(
                guarantee=guarantee,
                tenant_id=guarantee.tenant_id,
                image=image,
            )

    def _save_documents(self, guarantee):
        """Ajoute des documents (titles + files) et supprime ceux demandés."""
        request = self.context.get("request")
        if not request:
            return

        raw_delete = request.data.get("delete_document_ids") or "[]"
        if isinstance(raw_delete, str):
            try:
                delete_ids = json.loads(raw_delete or "[]")
            except json.JSONDecodeError:
                delete_ids = []
        else:
            delete_ids = list(raw_delete) if raw_delete else []
        if delete_ids:
            guarantee.documents.filter(id__in=delete_ids).delete()

        titles = request.data.getlist("document_titles") if hasattr(
            request.data, "getlist"
        ) else request.data.get("document_titles") or []
        if isinstance(titles, str):
            try:
                titles = json.loads(titles or "[]")
            except json.JSONDecodeError:
                titles = [titles] if titles.strip() else []
        from apps.common.upload_validation import validate_uploaded_file

        files = request.FILES.getlist("documents")
        for idx, uploaded in enumerate(files):
            title = ""
            if idx < len(titles):
                title = str(titles[idx] or "").strip()
            if not title:
                title = getattr(uploaded, "name", None) or f"Document {idx + 1}"
            validate_uploaded_file(uploaded, tenant=guarantee.tenant, check_quota=True)
            GuaranteeDocument.objects.create(
                guarantee=guarantee,
                tenant_id=guarantee.tenant_id,
                title=title[:200],
                file=uploaded,
            )

    def _save_jewelry_items(self, guarantee, items):
        """Remplace l'ensemble des composantes de bijou de la garantie."""
        if items is None:
            return
        guarantee.jewelry_items.all().delete()
        for item in items:
            GuaranteeJewelryItem.objects.create(
                guarantee=guarantee,
                tenant_id=guarantee.tenant_id,
                **item,
            )

    def create(self, validated_data):
        jewelry_items = validated_data.pop("jewelry_items", None)
        guarantee = super().create(validated_data)
        self._save_photos(guarantee)
        self._save_documents(guarantee)
        self._save_jewelry_items(guarantee, jewelry_items)
        return guarantee

    def update(self, instance, validated_data):
        jewelry_items = validated_data.pop("jewelry_items", None)
        guarantee = super().update(instance, validated_data)
        self._save_photos(guarantee)
        self._save_documents(guarantee)
        self._save_jewelry_items(guarantee, jewelry_items)
        return guarantee


class ReleaseFeeSerializer(serializers.ModelSerializer):
    fee_type_display = serializers.CharField(
        source="get_fee_type_display", read_only=True
    )
    payer_display = serializers.CharField(
        source="get_payer_display", read_only=True
    )

    class Meta:
        model = ReleaseFee
        fields = [
            "id",
            "fee_type",
            "fee_type_display",
            "label",
            "amount",
            "payer",
            "payer_display",
            "fee_date",
            "recoverable",
            "notes",
            "created_at",
        ]
        read_only_fields = fields


class ReleaseDocumentUploadSerializer(serializers.Serializer):
    file = serializers.FileField()
    name = serializers.CharField(required=False, allow_blank=True, max_length=255)
    category = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=50,
        help_text="Code GED (ex. ML_DEMANDE). Défaut : ML_OTHER.",
    )

    def validate_file(self, value):
        from apps.common.upload_validation import (
            resolve_tenant_from_context,
            validate_uploaded_file,
        )

        return validate_uploaded_file(
            value,
            tenant=resolve_tenant_from_context(self.context),
            check_quota=True,
        )


class GuaranteeReleaseRequestSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(
        source="get_status_display", read_only=True
    )
    acte_status_display = serializers.CharField(
        source="get_acte_status_display", read_only=True
    )
    guarantee_reference = serializers.CharField(
        source="guarantee.reference", read_only=True
    )
    client_display = serializers.SerializerMethodField()
    fees = ReleaseFeeSerializer(many=True, read_only=True)
    has_client_demande = serializers.SerializerMethodField()
    has_generated_acte = serializers.SerializerMethodField()
    has_signed_acte = serializers.SerializerMethodField()
    can_deposit_signed_acte = serializers.SerializerMethodField()
    acte_generated_url = serializers.SerializerMethodField()
    acte_signed_url = serializers.SerializerMethodField()

    class Meta:
        model = GuaranteeReleaseRequest
        fields = [
            "id",
            "reference",
            "guarantee",
            "guarantee_reference",
            "application",
            "loan",
            "agency",
            "cbs_loan_reference",
            "cbs_client_id",
            "cbs_settled",
            "cbs_outstanding",
            "cbs_currency",
            "cbs_checked_at",
            "cbs_raw",
            "request_date",
            "release_fees",
            "fees",
            "fees_client_total",
            "fees_institution_total",
            "acte_status",
            "acte_status_display",
            "acte_generated_at",
            "acte_signed_at",
            "acte_generated_url",
            "acte_signed_url",
            "has_client_demande",
            "has_generated_acte",
            "has_signed_acte",
            "can_deposit_signed_acte",
            "status",
            "status_display",
            "comment",
            "completed_at",
            "client_display",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "reference",
            "cbs_settled",
            "cbs_outstanding",
            "cbs_currency",
            "cbs_checked_at",
            "cbs_raw",
            "fees",
            "fees_client_total",
            "fees_institution_total",
            "acte_status",
            "acte_status_display",
            "acte_generated_at",
            "acte_signed_at",
            "acte_generated_url",
            "acte_signed_url",
            "has_client_demande",
            "has_generated_acte",
            "has_signed_acte",
            "can_deposit_signed_acte",
            "status",
            "completed_at",
            "created_at",
            "updated_at",
        ]

    def get_client_display(self, obj):
        client = obj.guarantee.client if obj.guarantee_id else None
        return getattr(client, "display_name", str(client)) if client else ""

    def get_has_client_demande(self, obj):
        from apps.guarantees.process_services import has_client_demande

        return has_client_demande(obj)

    def get_has_generated_acte(self, obj):
        return obj.has_generated_acte()

    def get_has_signed_acte(self, obj):
        return obj.has_signed_acte()

    def get_can_deposit_signed_acte(self, obj):
        request = self.context.get("request")
        user = getattr(request, "user", None) if request else None
        from apps.guarantees.process_services import user_can_deposit_release_acte

        return user_can_deposit_release_acte(user, obj)

    def get_acte_generated_url(self, obj):
        return file_download_url(obj.acte_generated) if obj.acte_generated else None

    def get_acte_signed_url(self, obj):
        return file_download_url(obj.acte_signed) if obj.acte_signed else None


class DationAssetSerializer(serializers.ModelSerializer):
    source_display = serializers.CharField(
        source="get_source_display", read_only=True
    )
    asset_type_display = serializers.CharField(
        source="get_asset_type_display", read_only=True
    )
    guarantee_reference = serializers.CharField(
        source="guarantee.reference", read_only=True, default=None
    )
    guarantee_type_display = serializers.CharField(
        source="guarantee.get_guarantee_type_display",
        read_only=True,
        default=None,
    )

    class Meta:
        model = DationAsset
        fields = [
            "id",
            "source",
            "source_display",
            "asset_type",
            "asset_type_display",
            "guarantee",
            "guarantee_reference",
            "guarantee_type_display",
            "description",
            "value",
            "notes",
            "created_at",
        ]
        read_only_fields = fields


class DationFeeSerializer(serializers.ModelSerializer):
    fee_type_display = serializers.CharField(
        source="get_fee_type_display", read_only=True
    )
    payer_display = serializers.CharField(
        source="get_payer_display", read_only=True
    )

    class Meta:
        model = DationFee
        fields = [
            "id",
            "asset",
            "fee_type",
            "fee_type_display",
            "label",
            "amount",
            "payer",
            "payer_display",
            "fee_date",
            "recoverable",
            "notes",
            "created_at",
        ]
        read_only_fields = fields


class DationDocumentUploadSerializer(serializers.Serializer):
    file = serializers.FileField()
    name = serializers.CharField(required=False, allow_blank=True, max_length=255)
    category = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=50,
        help_text="Code catégorie GED (ex. DAT_PHOTO). Défaut : DAT_OTHER.",
    )
    asset = serializers.UUIDField(
        required=False,
        allow_null=True,
        help_text="Optionnel : rattacher la pièce à un bien du dossier.",
    )

    def validate_file(self, value):
        from apps.common.upload_validation import (
            resolve_tenant_from_context,
            validate_uploaded_file,
        )

        return validate_uploaded_file(
            value,
            tenant=resolve_tenant_from_context(self.context),
            check_quota=True,
        )


class DationRequestSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(
        source="get_status_display", read_only=True
    )
    client_display = serializers.SerializerMethodField()
    application_reference = serializers.SerializerMethodField()
    collection_case_id = serializers.SerializerMethodField()
    assets = DationAssetSerializer(many=True, read_only=True)
    fees = DationFeeSerializer(many=True, read_only=True)
    assets_total_value = serializers.SerializerMethodField()
    covers_claim = serializers.SerializerMethodField()
    coverage_gap = serializers.SerializerMethodField()
    settlement = serializers.SerializerMethodField()

    class Meta:
        model = DationRequest
        fields = [
            "id",
            "reference",
            "client",
            "client_display",
            "application",
            "application_reference",
            "collection_case_id",
            "agency",
            "cbs_client_id",
            "cbs_total_outstanding",
            "cbs_currency",
            "cbs_checked_at",
            "cbs_raw",
            "asset_description",
            "asset_value",
            "assets",
            "fees",
            "assets_total_value",
            "fees_client_total",
            "fees_institution_total",
            "claim_to_cover",
            "residual_balance",
            "surplus_amount",
            "require_full_coverage",
            "settlement_notes",
            "covers_claim",
            "coverage_gap",
            "settlement",
            "status",
            "status_display",
            "comment",
            "resulting_guarantee",
            "completed_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "reference",
            "cbs_total_outstanding",
            "cbs_currency",
            "cbs_checked_at",
            "cbs_raw",
            "status",
            "resulting_guarantee",
            "completed_at",
            "created_at",
            "updated_at",
            "assets",
            "fees",
            "assets_total_value",
            "fees_client_total",
            "fees_institution_total",
            "claim_to_cover",
            "residual_balance",
            "surplus_amount",
            "covers_claim",
            "coverage_gap",
            "settlement",
            "application_reference",
            "collection_case_id",
        ]

    def get_application_reference(self, obj):
        app = obj.application
        if app is None:
            return ""
        return app.reference or str(app.id)

    def get_collection_case_id(self, obj):
        app = obj.application
        if app is None:
            return None
        try:
            loan = app.loan
        except Exception:  # noqa: BLE001
            return None
        case = getattr(loan, "collection_case", None)
        return str(case.id) if case is not None else None

    def get_client_display(self, obj):
        client = obj.client
        return getattr(client, "display_name", str(client)) if client else ""

    def get_assets_total_value(self, obj):
        return obj.assets_total_value()

    def get_covers_claim(self, obj):
        return obj.covers_claim()

    def get_coverage_gap(self, obj):
        data = obj.compute_settlement()
        if obj.cbs_total_outstanding is None:
            return None
        return data["coverage_gap"]

    def get_settlement(self, obj):
        data = obj.compute_settlement()
        return {k: (str(v) if hasattr(v, "quantize") else v) for k, v in data.items()}


class FormalizationFeeSerializer(serializers.ModelSerializer):
    fee_type_display = serializers.CharField(
        source="get_fee_type_display", read_only=True
    )
    payer_display = serializers.CharField(
        source="get_payer_display", read_only=True
    )

    class Meta:
        model = FormalizationFee
        fields = [
            "id",
            "fee_type",
            "fee_type_display",
            "label",
            "amount",
            "payer",
            "payer_display",
            "fee_date",
            "recoverable",
            "notes",
            "created_at",
        ]
        read_only_fields = fields


class FormalizationDocumentUploadSerializer(serializers.Serializer):
    file = serializers.FileField()
    name = serializers.CharField(required=False, allow_blank=True, max_length=255)
    category = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=50,
        help_text="Code GED (ex. FORM_ACTE_SIGNE). Défaut : FORM_OTHER.",
    )

    def validate_file(self, value):
        from apps.common.upload_validation import (
            resolve_tenant_from_context,
            validate_uploaded_file,
        )

        return validate_uploaded_file(
            value,
            tenant=resolve_tenant_from_context(self.context),
            check_quota=True,
        )


class GuaranteeFormalizationRequestSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(
        source="get_status_display", read_only=True
    )
    legal_stage_display = serializers.CharField(
        source="get_legal_stage_display", read_only=True
    )
    client = serializers.SerializerMethodField()
    client_display = serializers.SerializerMethodField()
    application_reference = serializers.SerializerMethodField()
    guarantee_reference = serializers.CharField(
        source="guarantee.reference", read_only=True, default=None
    )
    fees = FormalizationFeeSerializer(many=True, read_only=True)
    acte_file_url = serializers.SerializerMethodField()
    acte_signed_file_url = serializers.SerializerMethodField()
    registration_proof_url = serializers.SerializerMethodField()

    class Meta:
        model = GuaranteeFormalizationRequest
        fields = [
            "id",
            "reference",
            "guarantee",
            "guarantee_reference",
            "client",
            "client_display",
            "application",
            "application_reference",
            "agency",
            "status",
            "status_display",
            "legal_stage",
            "legal_stage_display",
            "notary_name",
            "notary_reference",
            "sent_to_notary_at",
            "expected_return_date",
            "registration_number",
            "registration_date",
            "registration_authority",
            "acte_file",
            "acte_file_url",
            "acte_signed_file",
            "acte_signed_file_url",
            "registration_proof",
            "registration_proof_url",
            "fees",
            "fees_client_total",
            "fees_institution_total",
            "comment",
            "completed_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "reference",
            "status",
            "status_display",
            "legal_stage_display",
            "fees",
            "fees_client_total",
            "fees_institution_total",
            "acte_file_url",
            "acte_signed_file_url",
            "registration_proof_url",
            "client",
            "client_display",
            "application_reference",
            "guarantee_reference",
            "completed_at",
            "created_at",
            "updated_at",
        ]

    def get_client(self, obj):
        client = obj.guarantee.client if obj.guarantee_id else None
        return str(client.pk) if client else None

    def get_client_display(self, obj):
        client = obj.guarantee.client if obj.guarantee_id else None
        return getattr(client, "display_name", str(client)) if client else ""

    def get_application_reference(self, obj):
        app = obj.application
        return getattr(app, "reference", None) if app else None

    def get_acte_file_url(self, obj):
        return file_download_url(obj.acte_file) if obj.acte_file else None

    def get_acte_signed_file_url(self, obj):
        return (
            file_download_url(obj.acte_signed_file)
            if obj.acte_signed_file
            else None
        )

    def get_registration_proof_url(self, obj):
        return (
            file_download_url(obj.registration_proof)
            if obj.registration_proof
            else None
        )

    def validate(self, attrs):
        from apps.common.upload_validation import validate_attrs_uploads

        return validate_attrs_uploads(attrs, self.context, check_quota=True)

    def to_representation(self, instance):
        return presign_file_fields(
            super().to_representation(instance),
            instance,
            "acte_file",
            "acte_signed_file",
            "registration_proof",
        )
