from decimal import Decimal

from rest_framework import serializers

from .models import (
    ApprovalCondition,
    ApprovalStep,
    ApprovalTask,
    BusinessCalendar,
    WorkflowDefinition,
    WorkflowInstance,
)


class BusinessCalendarSerializer(serializers.ModelSerializer):
    class Meta:
        model = BusinessCalendar
        fields = ["id", "code", "name", "timezone", "working_days", "opening_time", "closing_time", "holidays", "is_active", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate(self, attrs):
        from .calendars import validate_calendar
        from apps.common.tenancy import get_current_tenant_id
        code = attrs.get("code", getattr(self.instance, "code", None))
        duplicates = BusinessCalendar.all_tenants.filter(tenant_id=get_current_tenant_id(), code=code)
        if self.instance:
            duplicates = duplicates.exclude(pk=self.instance.pk)
        if duplicates.exists():
            raise serializers.ValidationError({"code": "Ce code existe déjà dans la filiale."})
        values = {name: attrs.get(name, getattr(self.instance, name, default)) for name, default in {
            "timezone": "UTC", "working_days": [0, 1, 2, 3, 4], "opening_time": "08:00", "closing_time": "17:00", "holidays": [],
        }.items()}
        try:
            validate_calendar(values)
        except (ValueError, TypeError) as exc:
            raise serializers.ValidationError({"calendar": str(exc)})
        return attrs


class ApprovalStepSerializer(serializers.ModelSerializer):
    committee_quorum = serializers.IntegerField(min_value=1, max_value=100, required=False)
    order = serializers.IntegerField(min_value=1, required=False)
    sla_hours = serializers.IntegerField(min_value=0, max_value=87600, required=False)
    min_risk_level = serializers.IntegerField(min_value=0, max_value=5, allow_null=True, required=False)
    committee_majority_numerator = serializers.IntegerField(min_value=1, max_value=1000, required=False)
    committee_majority_denominator = serializers.IntegerField(min_value=1, max_value=1000, required=False)

    def validate(self, attrs):
        from apps.accounts.models import TenantRole
        from apps.accounts.services import GROUP_CREDIT_COMMITTEE_DJANGO_GROUP

        definition = attrs.get("definition", getattr(self.instance, "definition", None))
        from apps.common.tenancy import get_current_tenant_id
        if definition and str(definition.tenant_id) != str(get_current_tenant_id()):
            raise serializers.ValidationError({"definition": "Le circuit doit appartenir à la filiale sélectionnée."})
        group = attrs.get("required_group", getattr(self.instance, "required_group", None))
        if definition and group:
            if not TenantRole.objects.filter(tenant_id=definition.tenant_id, group=group).exists() and group.name != GROUP_CREDIT_COMMITTEE_DJANGO_GROUP:
                raise serializers.ValidationError({
                    "required_group": "Le rôle doit appartenir à la filiale du circuit ou être le comité Groupe."
                })
        if self.instance and definition and definition.pk != self.instance.definition_id:
            raise serializers.ValidationError({"definition": "Une étape ne peut pas être déplacée vers un autre circuit."})
        low = attrs.get("min_amount", getattr(self.instance, "min_amount", None))
        high = attrs.get("max_amount", getattr(self.instance, "max_amount", None))
        if (low is not None and low < 0) or (high is not None and high < 0) or (low is not None and high is not None and low > high):
            raise serializers.ValidationError({"max_amount": "Les bornes doivent être positives et le plafond supérieur ou égal au plancher."})
        numerator = attrs.get("committee_majority_numerator", getattr(self.instance, "committee_majority_numerator", 2))
        denominator = attrs.get("committee_majority_denominator", getattr(self.instance, "committee_majority_denominator", 3))
        if numerator > denominator or numerator * 2 <= denominator:
            raise serializers.ValidationError({"committee_majority_numerator": "La majorité qualifiée doit être strictement supérieure à 1/2 et au plus égale à 1."})
        if attrs.get("sla_mode", getattr(self.instance, "sla_mode", "CALENDAR")) == "BUSINESS" and definition and not definition.business_calendar_id:
            raise serializers.ValidationError({"sla_mode": "Associez d'abord un calendrier ouvré au circuit."})
        return attrs

    class Meta:
        model = ApprovalStep
        fields = [
            "id", "definition", "name", "order", "required_group", "mode",
            "step_kind", "min_amount", "max_amount", "min_risk_level",
            "sla_hours", "allow_return", "committee_quorum",
            "sla_mode", "committee_enabled", "committee_majority", "committee_majority_numerator",
            "committee_majority_denominator", "committee_abstentions", "committee_record_required", "committee_pv_required",
        ]
        read_only_fields = ["id"]


class WorkflowDefinitionSerializer(serializers.ModelSerializer):
    version = serializers.IntegerField(min_value=1, required=False)
    steps = ApprovalStepSerializer(many=True, read_only=True)
    is_used = serializers.SerializerMethodField()
    decision_gaps = serializers.SerializerMethodField()
    product_label = serializers.SerializerMethodField()
    product_category_label = serializers.SerializerMethodField()
    specificity_score = serializers.SerializerMethodField()

    class Meta:
        model = WorkflowDefinition
        fields = [
            "id",
            "code",
            "name",
            "target_type",
            "version",
            "is_active",
            "execution_mode", "business_calendar",
            "is_used",
            "decision_gaps",
            "min_amount",
            "max_amount",
            "product",
            "product_label",
            "product_category",
            "product_category_label",
            "specificity_score",
            "steps",
        ]
        read_only_fields = [
            "id",
            "is_used",
            "decision_gaps",
            "product_label",
            "product_category_label",
            "specificity_score",
        ]

    def get_is_used(self, obj):
        from .services import definition_is_used

        return definition_is_used(obj)

    def get_product_label(self, obj):
        return obj.product.label if obj.product_id else None

    def get_product_category_label(self, obj):
        return obj.product_category.label if obj.product_category_id else None

    def get_specificity_score(self, obj):
        return obj.specificity_score()

    def validate(self, attrs):
        from apps.common.tenancy import get_current_tenant_id
        if self.instance is None:
            if attrs.get("is_active") is True:
                raise serializers.ValidationError({"is_active": "Créez le circuit inactif, ajoutez les étapes puis activez-le."})
            attrs["is_active"] = False
        duplicates = WorkflowDefinition.all_tenants.filter(
            tenant_id=get_current_tenant_id(), code=attrs.get("code", getattr(self.instance, "code", None)),
            version=attrs.get("version", getattr(self.instance, "version", 1)),
        )
        if self.instance:
            duplicates = duplicates.exclude(pk=self.instance.pk)
        if duplicates.exists():
            raise serializers.ValidationError({"version": "Cette version du circuit existe déjà dans la filiale."})
        min_amount = attrs.get(
            "min_amount", getattr(self.instance, "min_amount", None)
        )
        max_amount = attrs.get(
            "max_amount", getattr(self.instance, "max_amount", None)
        )
        if (
            min_amount is not None
            and max_amount is not None
            and min_amount > max_amount
        ):
            raise serializers.ValidationError(
                {"max_amount": "Le plafond doit être supérieur ou égal au plancher."}
            )
        if (min_amount is not None and min_amount < 0) or (max_amount is not None and max_amount < 0):
            raise serializers.ValidationError({"min_amount": "Les montants du circuit doivent être positifs ou nuls."})

        product = attrs.get("product", getattr(self.instance, "product", None))
        category = attrs.get(
            "product_category", getattr(self.instance, "product_category", None)
        )
        if product is not None and category is not None:
            if product.category_id != category.id:
                raise serializers.ValidationError(
                    {
                        "product": (
                            "Le produit n'appartient pas à la famille sélectionnée."
                        )
                    }
                )
        calendar = attrs.get("business_calendar", getattr(self.instance, "business_calendar", None))
        for field, value in (("product", product), ("product_category", category), ("business_calendar", calendar)):
            if value is not None and str(value.tenant_id) != str(get_current_tenant_id()):
                raise serializers.ValidationError({field: "La référence doit appartenir à la filiale sélectionnée."})
        if calendar is not None and not calendar.is_active and "business_calendar" in attrs:
            raise serializers.ValidationError({"business_calendar": "Choisissez un calendrier actif."})
        return attrs

    def get_decision_gaps(self, obj):
        """Tranches de montant sans décideur, ou `null` si le circuit est sain.

        `obj.steps.all()` exploite le prefetch de la vue : pas de requête par
        circuit dans la liste.
        """
        from .services import compute_decision_gaps, format_decision_gaps

        gaps = compute_decision_gaps(obj, steps=obj.steps.all())
        if not gaps:
            return None
        return {
            "label": format_decision_gaps(gaps),
            "ranges": [
                {"from": str(low), "to": None if high is None else str(high)}
                for low, high in gaps
            ],
        }


class ApprovalTaskSerializer(serializers.ModelSerializer):
    committee_quorum = serializers.IntegerField(source="step.committee_quorum", read_only=True)
    committee_majority = serializers.CharField(source="step.committee_majority", read_only=True)
    committee_majority_numerator = serializers.IntegerField(source="step.committee_majority_numerator", read_only=True)
    committee_majority_denominator = serializers.IntegerField(source="step.committee_majority_denominator", read_only=True)
    committee_abstentions = serializers.CharField(source="step.committee_abstentions", read_only=True)
    committee_pv_required = serializers.BooleanField(source="step.committee_pv_required", read_only=True)
    committee_record_required = serializers.BooleanField(source="step.committee_record_required", read_only=True)
    sla_mode = serializers.CharField(source="step.sla_mode", read_only=True)
    is_committee = serializers.SerializerMethodField()

    def get_is_committee(self, obj):
        from .services import is_credit_committee_step
        return is_credit_committee_step(obj.step)
    step_name = serializers.CharField(source="step.name", read_only=True)
    step_order = serializers.IntegerField(source="step.order", read_only=True)
    step_kind = serializers.CharField(source="step.step_kind", read_only=True)
    allow_return = serializers.BooleanField(source="step.allow_return", read_only=True)
    acted_by_display = serializers.SerializerMethodField()
    opinion_display = serializers.CharField(
        source="get_opinion_display", read_only=True
    )
    application = serializers.SerializerMethodField()
    target_meta = serializers.SerializerMethodField()

    def get_acted_by_display(self, obj):
        return str(obj.acted_by) if obj.acted_by_id else ""

    class Meta:
        model = ApprovalTask
        fields = [
            "id", "instance", "step", "step_name", "step_order", "step_kind",
            "allow_return", "status", "opinion", "opinion_display",
            "decision_comment", "reject_reason", "proposed_amount",
            "acted_by", "acted_by_display", "acted_at", "due_at", "application",
            "target_meta", "decision_snapshot", "committee_record", "committee_quorum", "is_committee",
            "committee_majority", "committee_majority_numerator", "committee_majority_denominator",
            "committee_abstentions", "committee_pv_required", "committee_record_required", "sla_mode",
        ]
        read_only_fields = fields

    def get_target_meta(self, obj):
        target = obj.instance.target
        if target is None:
            return None
        from apps.credits.models import CreditApplication
        from apps.guarantees.models import (
            DationRequest,
            GuaranteeFormalizationRequest,
            GuaranteeReleaseRequest,
        )

        if isinstance(target, CreditApplication):
            return {
                "kind": "CREDIT",
                "id": str(target.id),
                "reference": target.reference,
                "detail_path": f"/dossiers/{target.id}",
            }
        if isinstance(target, GuaranteeReleaseRequest):
            return {
                "kind": "MAIN_LEVEE",
                "id": str(target.id),
                "reference": target.reference,
                "detail_path": f"/mains-levees/{target.id}",
            }
        if isinstance(target, DationRequest):
            return {
                "kind": "DATION",
                "id": str(target.id),
                "reference": target.reference,
                "detail_path": f"/dations/{target.id}",
            }
        if isinstance(target, GuaranteeFormalizationRequest):
            return {
                "kind": "FORMALISATION",
                "id": str(target.id),
                "reference": target.reference,
                "detail_path": f"/formalisations/{target.id}",
            }
        return {
            "kind": target.__class__.__name__,
            "id": str(target.pk),
            "reference": getattr(target, "reference", ""),
            "detail_path": None,
        }

    def get_application(self, obj):
        target = obj.instance.target
        from apps.credits.models import CreditApplication

        if not isinstance(target, CreditApplication):
            return None
        client = target.client
        return {
            "id": str(target.id),
            "reference": target.reference,
            "client_display": getattr(client, "display_name", str(client)),
            "amount_requested": str(target.amount_requested),
            "amount_proposed": (
                str(target.amount_proposed)
                if target.amount_proposed is not None
                else None
            ),
            "currency": target.currency,
        }


class ApprovalConditionSerializer(serializers.ModelSerializer):
    issued_by_display = serializers.SerializerMethodField()
    lifted_by_display = serializers.SerializerMethodField()
    validated_by_display = serializers.SerializerMethodField()
    step_name = serializers.CharField(source="task.step.name", read_only=True)
    can_lift = serializers.SerializerMethodField()
    can_validate = serializers.SerializerMethodField()

    def get_issued_by_display(self, obj):
        return str(obj.issued_by) if obj.issued_by_id else ""

    def get_lifted_by_display(self, obj):
        return str(obj.lifted_by) if obj.lifted_by_id else ""

    def get_validated_by_display(self, obj):
        return str(obj.validated_by) if obj.validated_by_id else ""

    class Meta:
        model = ApprovalCondition
        fields = [
            "id", "application", "task", "step_name", "description", "status",
            "issued_by", "issued_by_display", "issued_at",
            "lifted_by", "lifted_by_display", "lifted_at", "lift_comment",
            "validated_by", "validated_by_display", "validated_at",
            "validation_comment", "can_lift", "can_validate", "created_at",
        ]
        read_only_fields = fields

    def get_can_lift(self, obj):
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return False
        user = request.user
        app = obj.application
        if user.is_superuser or getattr(user, "is_group_level", False):
            return obj.status == ApprovalCondition.Status.PENDING
        return (
            obj.status == ApprovalCondition.Status.PENDING
            and user.id in {app.submitted_by_id, app.created_by_id}
        )

    def get_can_validate(self, obj):
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return False
        user = request.user
        if obj.status != ApprovalCondition.Status.LIFTED:
            return False
        return user.is_superuser or obj.issued_by_id == user.id


class WorkflowInstanceSerializer(serializers.ModelSerializer):
    tasks = ApprovalTaskSerializer(many=True, read_only=True)
    definition_code = serializers.CharField(source="definition.code", read_only=True)

    class Meta:
        model = WorkflowInstance
        fields = [
            "id", "definition", "definition_code", "content_type", "object_id",
            "status", "current_order", "amount", "risk_level", "tasks",
            "created_at",
            "calendar_snapshot",
        ]
        read_only_fields = fields


class DecisionSerializer(serializers.Serializer):
    committee_record = serializers.JSONField(required=False)
    decision = serializers.ChoiceField(
        choices=["APPROVED", "REJECTED", "RETURNED"]
    )
    opinion = serializers.ChoiceField(
        choices=[
            "FAVORABLE",
            "FAVORABLE_SOUS_RESERVE",
            "DEFAVORABLE",
        ],
        required=False,
        allow_blank=True,
    )
    comment = serializers.CharField(required=False, allow_blank=True)
    reserves = serializers.ListField(
        child=serializers.CharField(max_length=2000),
        required=False,
        allow_empty=True,
    )
    reject_reason = serializers.UUIDField(required=False, allow_null=True)
    proposed_amount = serializers.DecimalField(
        max_digits=18, decimal_places=2, required=False, allow_null=True,
        min_value=Decimal("0"),
    )
    # Pour un renvoi (RETURNED) : True = renvoyer directement au soumissionnaire
    # (le dossier repasse en correction) ; False/absent = renvoyer à l'étape
    # inférieure (comportement par défaut).
    return_to_submitter = serializers.BooleanField(required=False, default=False)


class ConditionActionSerializer(serializers.Serializer):
    comment = serializers.CharField(required=False, allow_blank=True, default="")
