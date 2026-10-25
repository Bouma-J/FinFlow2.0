import json

from rest_framework import serializers

from apps.clients.serializers import PhonesInputField
from apps.common.storage_urls import file_download_url, presign_file_fields

from .models import Surety, SuretyDocument, SuretyEngagement, SuretyPhone


class SuretyEngagementSerializer(serializers.ModelSerializer):
    surety_display = serializers.CharField(
        source="surety.display_name", read_only=True
    )
    surety_activity = serializers.CharField(
        source="surety.activity", read_only=True
    )
    surety_type = serializers.CharField(
        source="surety.surety_type", read_only=True
    )
    surety_id_document_scan = serializers.FileField(
        source="surety.id_document_scan", read_only=True
    )
    surety_photo = serializers.ImageField(
        source="surety.photo", read_only=True
    )
    status_display = serializers.CharField(
        source="get_status_display", read_only=True
    )
    engagement_type_display = serializers.CharField(
        source="get_engagement_type_display", read_only=True
    )
    application_reference = serializers.CharField(
        source="application.reference", read_only=True, default=None
    )
    client_display = serializers.SerializerMethodField()
    contract_id = serializers.SerializerMethodField()
    contract_status = serializers.SerializerMethodField()
    contract_status_display = serializers.SerializerMethodField()
    contract_file_url = serializers.SerializerMethodField()
    contract_signed_file_url = serializers.SerializerMethodField()
    contract_template_name = serializers.SerializerMethodField()

    class Meta:
        model = SuretyEngagement
        fields = [
            "id",
            "surety",
            "surety_display",
            "surety_activity",
            "surety_type",
            "surety_id_document_scan",
            "surety_photo",
            "application",
            "application_reference",
            "client_display",
            "amount",
            "engagement_type",
            "engagement_type_display",
            "signed_date",
            "status",
            "status_display",
            "notes",
            "released_at",
            "called_at",
            "contract_id",
            "contract_status",
            "contract_status_display",
            "contract_file_url",
            "contract_signed_file_url",
            "contract_template_name",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "status",
            "released_at",
            "called_at",
            "created_at",
        ]

    def get_client_display(self, obj) -> str:
        client = getattr(obj.application, "client", None)
        if not client:
            return ""
        return getattr(client, "display_name", str(client))

    def _contract(self, obj):
        return obj.active_contract

    def get_contract_id(self, obj):
        c = self._contract(obj)
        return str(c.id) if c else None

    def get_contract_status(self, obj):
        c = self._contract(obj)
        return c.status if c else None

    def get_contract_status_display(self, obj):
        c = self._contract(obj)
        return c.get_status_display() if c else None

    def get_contract_file_url(self, obj):
        c = self._contract(obj)
        return file_download_url(c.file) if c and c.file else None

    def get_contract_signed_file_url(self, obj):
        c = self._contract(obj)
        return (
            file_download_url(c.signed_file)
            if c and c.signed_file
            else None
        )

    def get_contract_template_name(self, obj):
        c = self._contract(obj)
        return c.template_name if c else None

    def to_representation(self, instance):
        data = super().to_representation(instance)
        surety = instance.surety
        data["surety_id_document_scan"] = (
            file_download_url(surety.id_document_scan)
            if surety and surety.id_document_scan
            else None
        )
        data["surety_photo"] = (
            file_download_url(surety.photo)
            if surety and surety.photo
            else None
        )
        return data


class SuretyPhoneSerializer(serializers.ModelSerializer):
    class Meta:
        model = SuretyPhone
        fields = ["id", "number", "label"]


class SuretyDocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = SuretyDocument
        fields = ["id", "title", "file", "created_at"]
        read_only_fields = ["id", "created_at"]

    def to_representation(self, instance):
        return presign_file_fields(
            super().to_representation(instance), instance, "file"
        )


class SuretyListSerializer(serializers.ModelSerializer):
    """Liste allégée — résumé des engagements ouverts (client / crédit / caution)."""

    display_name = serializers.CharField(read_only=True)
    total_committed = serializers.DecimalField(
        max_digits=18, decimal_places=2, read_only=True
    )
    available_ceiling = serializers.DecimalField(
        max_digits=18, decimal_places=2, read_only=True
    )
    client_display = serializers.SerializerMethodField()
    credit_amount = serializers.SerializerMethodField()
    credit_currency = serializers.SerializerMethodField()
    guaranteed_amount = serializers.SerializerMethodField()

    class Meta:
        model = Surety
        fields = [
            "id", "surety_type", "display_name", "agency", "phone", "city",
            "activity",
            "client_display", "credit_amount", "credit_currency",
            "guaranteed_amount",
            "commitment_ceiling", "total_committed", "available_ceiling",
            "is_active", "created_at",
        ]
        read_only_fields = fields

    def _open_engagements(self, obj):
        cached = getattr(obj, "_prefetched_objects_cache", {}).get("engagements")
        if cached is not None:
            open_statuses = {
                SuretyEngagement.Status.ACTIVE,
                SuretyEngagement.Status.CALLED,
            }
            rows = [e for e in cached if e.status in open_statuses]
            rows.sort(key=lambda e: e.created_at or e.pk, reverse=True)
            return rows
        return list(
            obj.engagements.filter(
                status__in=[
                    SuretyEngagement.Status.ACTIVE,
                    SuretyEngagement.Status.CALLED,
                ]
            )
            .select_related("application", "application__client")
            .order_by("-created_at")
        )

    def get_client_display(self, obj):
        engagements = self._open_engagements(obj)
        if not engagements:
            return ""
        names = []
        seen = set()
        for eng in engagements:
            client = getattr(eng.application, "client", None)
            if not client:
                continue
            label = (getattr(client, "display_name", None) or str(client)).strip()
            if not label or label in seen:
                continue
            seen.add(label)
            names.append(label)
        if not names:
            return ""
        if len(names) == 1:
            return names[0]
        return f"{names[0]} (+{len(names) - 1})"

    def get_credit_amount(self, obj):
        engagements = self._open_engagements(obj)
        if not engagements:
            return None
        app = engagements[0].application
        if app is None:
            return None
        for attr in ("amount_approved", "amount_proposed", "amount_requested"):
            value = getattr(app, attr, None)
            if value is not None:
                return value
        return None

    def get_credit_currency(self, obj):
        engagements = self._open_engagements(obj)
        if not engagements or engagements[0].application is None:
            return None
        return getattr(engagements[0].application, "currency", None) or None

    def get_guaranteed_amount(self, obj):
        engagements = self._open_engagements(obj)
        if not engagements:
            return None
        if len(engagements) == 1:
            return engagements[0].amount
        return obj.total_committed


class SuretySerializer(serializers.ModelSerializer):
    display_name = serializers.CharField(read_only=True)
    engagements = SuretyEngagementSerializer(many=True, read_only=True)
    phones = SuretyPhoneSerializer(many=True, read_only=True)
    documents = SuretyDocumentSerializer(many=True, read_only=True)
    additional_phones = PhonesInputField(write_only=True, required=False)
    total_committed = serializers.DecimalField(
        max_digits=18, decimal_places=2, read_only=True
    )
    available_ceiling = serializers.DecimalField(
        max_digits=18, decimal_places=2, read_only=True
    )

    class Meta:
        model = Surety
        fields = [
            "id", "surety_type", "display_name", "name", "agency",
            # Identité physique
            "first_name", "last_name", "birth_date", "birth_country",
            "activity", "estimated_income",
            # Pièce d'identité
            "id_document_type", "national_id", "id_document_issue_date",
            "id_document_expiry_date", "id_document_scan", "photo",
            # Entreprise
            "company_name", "legal_form", "ifu", "rccm",
            "ifu_scan", "rccm_scan", "city",
            # Gérant
            "manager_last_name", "manager_first_name", "manager_phone",
            "manager_email", "manager_address", "manager_id_document_type",
            "manager_id_document_number", "manager_id_document_issue_date",
            "manager_id_document_expiry_date", "manager_id_document_scan",
            "manager_position", "manager_birth_date", "manager_birth_country",
            "manager_birth_city",
            # Coordonnées
            "identifier", "phone", "email", "address",
            "phones", "additional_phones",
            # Documents libres
            "documents",
            # Engagement
            "commitment_ceiling", "total_committed", "available_ceiling",
            "is_active", "engagements", "created_at",
        ]
        read_only_fields = ["id", "is_active", "created_at"]

    def validate(self, attrs):
        from apps.common.upload_validation import validate_attrs_uploads

        attrs = validate_attrs_uploads(attrs, self.context, check_quota=True)
        surety_type = attrs.get("surety_type") or getattr(
            self.instance, "surety_type", Surety.SuretyType.PHYSICAL
        )
        if surety_type == Surety.SuretyType.MORAL:
            company = attrs.get("company_name") or getattr(
                self.instance, "company_name", ""
            )
            name = attrs.get("name") or getattr(self.instance, "name", "")
            if not (company or name):
                raise serializers.ValidationError(
                    {"company_name": "La raison sociale de la caution est obligatoire."}
                )
        else:
            last_name = attrs.get("last_name") or getattr(
                self.instance, "last_name", ""
            )
            name = attrs.get("name") or getattr(self.instance, "name", "")
            if not (last_name or name):
                raise serializers.ValidationError(
                    {"last_name": "Le nom de la caution est obligatoire."}
                )
        return attrs

    def to_representation(self, instance):
        return presign_file_fields(
            super().to_representation(instance),
            instance,
            "id_document_scan",
            "photo",
            "ifu_scan",
            "rccm_scan",
            "manager_id_document_scan",
        )

    def _sync_phones(self, surety, phones):
        for entry in phones:
            SuretyPhone.objects.create(
                surety=surety, number=entry["number"], label=entry.get("label", "")
            )

    def _save_documents(self, surety):
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
            surety.documents.filter(id__in=delete_ids).delete()

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
            validate_uploaded_file(uploaded, tenant=surety.tenant, check_quota=True)
            SuretyDocument.objects.create(
                surety=surety,
                tenant_id=surety.tenant_id,
                title=title[:200],
                file=uploaded,
            )

    def create(self, validated_data):
        phones = validated_data.pop("additional_phones", None)
        surety = super().create(validated_data)
        if phones:
            self._sync_phones(surety, phones)
        self._save_documents(surety)
        return surety

    def update(self, instance, validated_data):
        phones = validated_data.pop("additional_phones", None)
        surety = super().update(instance, validated_data)
        if phones is not None:
            instance.phones.all().delete()
            self._sync_phones(surety, phones)
        self._save_documents(surety)
        return surety
