from django.contrib.auth.models import Group, Permission
from django.db import transaction
from rest_framework import serializers

from apps.common.tenancy import get_current_tenant_id
from apps.tenants.models import Agency

from .models import DataScope, Delegation, TenantRole, User
from .capabilities import CAPABILITIES
from .services import (
    create_tenant_role,
    validate_groups_for_tenant,
    validate_sod_role_assignment,
)


def validate_account_administration(attrs, instance, context):
    """Un gestionnaire filiale ne peut créer ni déplacer un compte hors filiale."""
    request = context.get("request")
    actor = getattr(request, "user", None)
    if not actor or actor.is_superuser or actor.is_group_level:
        return
    tenant = attrs.get("tenant", getattr(instance, "tenant", None))
    if attrs.get("is_group_level", getattr(instance, "is_group_level", False)):
        raise serializers.ValidationError({
            "is_group_level": "Seul le niveau Groupe peut gérer des comptes Groupe."
        })
    if not actor.tenant_id or (tenant and tenant.pk != actor.tenant_id):
        raise serializers.ValidationError({
            "tenant": "Vous ne pouvez gérer que les utilisateurs de votre filiale."
        })


class PermissionSerializer(serializers.ModelSerializer):
    label = serializers.SerializerMethodField()
    app_label = serializers.CharField(
        source="content_type.app_label", read_only=True
    )
    model = serializers.CharField(source="content_type.model", read_only=True)

    class Meta:
        model = Permission
        fields = ["id", "name", "codename", "app_label", "model", "label"]

    def get_label(self, obj):
        return f"{obj.content_type.app_label}.{obj.codename}"


class GroupSerializer(serializers.ModelSerializer):
    """Sérialiseur legacy — préférer TenantRoleSerializer."""

    permissions = serializers.PrimaryKeyRelatedField(
        many=True, queryset=Permission.objects.all(), required=False
    )
    permissions_detail = PermissionSerializer(
        source="permissions", many=True, read_only=True
    )
    user_count = serializers.SerializerMethodField()

    class Meta:
        model = Group
        fields = ["id", "name", "permissions", "permissions_detail", "user_count"]

    def get_user_count(self, obj):
        return obj.user_set.count()


class TenantRoleSerializer(serializers.ModelSerializer):
    """Rôle filiale exposé via l'API /roles/."""

    id = serializers.IntegerField(source="group.id", read_only=True)
    tenant = serializers.UUIDField(source="tenant_id", read_only=True)
    permissions = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=Permission.objects.all(),
        source="group.permissions",
        required=False,
    )
    permissions_detail = PermissionSerializer(
        source="group.permissions", many=True, read_only=True
    )
    user_count = serializers.SerializerMethodField()
    capabilities = serializers.ListField(child=serializers.ChoiceField(choices=CAPABILITIES), max_length=len(CAPABILITIES), required=False)

    def validate_capabilities(self, values):
        if len(values) != len(set(values)):
            raise serializers.ValidationError("Une fonction ne peut figurer qu'une seule fois.")
        return values

    class Meta:
        model = TenantRole
        fields = [
            "id", "tenant", "name", "permissions", "permissions_detail",
            "user_count", "created_at", "capabilities", "pack_code",
        ]
        read_only_fields = ["id", "tenant", "created_at", "pack_code"]

    def to_representation(self, instance):
        from .capabilities import group_capabilities
        # capabilities n'est pas un champ du modèle ; sa source est le groupe.
        instance.capabilities = sorted(group_capabilities(instance.group))
        return super().to_representation(instance)

    def _permissions(self, group_data, capabilities, existing=None):
        from .capabilities import group_capabilities, validate_capability_combination
        from .services import capability_permissions

        codes = set(capabilities) if capabilities is not None else group_capabilities(existing)
        try:
            validate_capability_combination(codes)
            if existing is not None:
                # Changer un rôle ne doit pas contourner la vérification faite
                # lors de l'affectation des rôles à chacun de ses utilisateurs.
                for user in existing.user_set.select_for_update().order_by("pk"):
                    combined = set(codes)
                    for other in user.groups.exclude(pk=existing.pk):
                        combined.update(group_capabilities(other))
                    validate_capability_combination(combined)
        except ValueError as exc:
            raise serializers.ValidationError({"capabilities": str(exc)}) from exc
        base = group_data.get("permissions")
        if base is None:
            base = list(existing.permissions.all()) if existing else []
        base = [p for p in base if not (p.content_type.app_label == "accounts" and p.codename.startswith("business_"))]
        return [*base, *capability_permissions(codes)]

    def get_user_count(self, obj):
        return obj.group.user_set.count()

    @transaction.atomic
    def create(self, validated_data):
        tenant_id = get_current_tenant_id()
        if tenant_id is None:
            raise serializers.ValidationError(
                "Aucune filiale sélectionnée. Choisissez une filiale avant "
                "de créer un rôle."
            )
        from apps.tenants.models import Tenant

        tenant = Tenant.objects.get(pk=tenant_id)
        group_data = validated_data.pop("group", {})
        permissions = self._permissions(group_data, validated_data.pop("capabilities", None))
        name = validated_data["name"]
        if TenantRole.objects.filter(tenant=tenant, name=name).exists():
            raise serializers.ValidationError(
                {"name": "Un rôle avec ce nom existe déjà pour cette filiale."}
            )
        return create_tenant_role(tenant, name, permissions)

    @transaction.atomic
    def update(self, instance, validated_data):
        instance = TenantRole.objects.select_for_update().select_related("group").get(pk=instance.pk)
        capabilities = validated_data.pop("capabilities", None)
        group_data = validated_data.get("group", {})
        permissions = self._permissions(group_data, capabilities, instance.group)
        if "name" in validated_data:
            if TenantRole.objects.filter(tenant=instance.tenant, name=validated_data["name"]).exclude(pk=instance.pk).exists():
                raise serializers.ValidationError({"name": "Un rôle avec ce nom existe déjà pour cette filiale."})
            instance.name = validated_data["name"]
            instance.save(update_fields=["name"])
        if "permissions" in group_data or capabilities is not None:
            instance.group.permissions.set(permissions)
        return instance


class TenantRoleOptionSerializer(serializers.ModelSerializer):
    """Compact list representation used by role selectors and summaries."""

    id = serializers.IntegerField(source="group.id", read_only=True)
    tenant = serializers.UUIDField(source="tenant_id", read_only=True)
    permission_count = serializers.IntegerField(read_only=True)
    user_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = TenantRole
        fields = ["id", "tenant", "name", "permission_count", "user_count", "pack_code"]


class UserGroupSerializer(serializers.ModelSerializer):
    name = serializers.SerializerMethodField()

    class Meta:
        model = Group
        fields = ["id", "name"]

    def get_name(self, obj):
        from apps.accounts.utils import _role_name

        return _role_name(obj)


class AgencySummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = Agency
        fields = ["id", "code", "name"]


class UserSerializer(serializers.ModelSerializer):
    groups = UserGroupSerializer(many=True, read_only=True)
    group_ids = serializers.PrimaryKeyRelatedField(
        many=True, queryset=Group.objects.all(), source="groups",
        write_only=True, required=False,
    )
    agencies_detail = AgencySummarySerializer(
        source="agencies", many=True, read_only=True
    )
    agency_ids = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=Agency.objects.all(),
        source="agencies",
        write_only=True,
        required=False,
    )

    class Meta:
        model = User
        fields = [
            "id", "username", "email", "first_name", "last_name",
            "tenant", "agency", "agencies_detail", "agency_ids",
            "data_scope", "is_group_level", "is_staff", "employee_id",
            "cbs_id", "phone", "mfa_enabled", "must_change_password", "is_active",
            "groups", "group_ids",
            "date_joined", "last_login",
        ]
        read_only_fields = [
            "id", "date_joined", "last_login", "is_staff", "must_change_password",
        ]

    def validate_cbs_id(self, value):
        from apps.catalog.cbs_validation import validate_manager_cbs_id

        tenant_id = None
        if self.instance is not None:
            tenant_id = self.instance.tenant_id
        elif self.initial_data.get("tenant"):
            tenant_id = self.initial_data.get("tenant")
        else:
            from apps.common.tenancy import get_current_tenant_id

            tenant_id = get_current_tenant_id()
        return validate_manager_cbs_id(value, tenant_id=tenant_id)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        user = getattr(request, "user", None) if request else None
        # Seul un admin Groupe peut élever/révoquer is_staff sur un user filiale
        if user and (
            getattr(user, "is_group_level", False) or user.is_superuser
        ):
            self.fields["is_staff"].read_only = False

    def validate(self, attrs):
        validate_account_administration(attrs, self.instance, self.context)
        request = self.context.get("request")
        actor = getattr(request, "user", None) if request else None
        if "is_staff" in attrs:
            if not (
                actor
                and (
                    getattr(actor, "is_group_level", False)
                    or actor.is_superuser
                )
            ):
                raise serializers.ValidationError({
                    "is_staff": "Seul un administrateur Groupe peut modifier ce droit."
                })
            # Interdit d'élever un user Groupe via ce champ hors provision dédiée
            target = self.instance
            is_group = attrs.get(
                "is_group_level",
                getattr(target, "is_group_level", False) if target else False,
            )
            if is_group and not attrs.get("is_staff", True):
                pass  # autoriser désactivation staff groupe
        groups = attrs.get("groups")
        if groups is not None:
            tenant = attrs.get("tenant", getattr(self.instance, "tenant", None))
            if tenant is not None:
                try:
                    validate_groups_for_tenant(tenant.id, groups)
                    validate_sod_role_assignment(groups)
                except ValueError as exc:
                    raise serializers.ValidationError({"group_ids": str(exc)})
        return self._validate_user_scope(attrs)

    def _validate_user_scope(self, attrs):
        is_group = attrs.get(
            "is_group_level",
            getattr(self.instance, "is_group_level", False),
        )
        tenant = attrs.get("tenant", getattr(self.instance, "tenant", None))
        agency = attrs.get("agency", getattr(self.instance, "agency", None))
        agencies = attrs.get("agencies")
        if agencies is None and self.instance is not None:
            agencies = list(self.instance.agencies.all())
        data_scope = attrs.get(
            "data_scope",
            getattr(self.instance, "data_scope", DataScope.AGENCY),
        )

        if not is_group:
            if tenant is None:
                raise serializers.ValidationError({"tenant": "La filiale est obligatoire."})
            # Admin filiale (TENANT) : agence non obligatoire.
            if agency is None and data_scope != DataScope.TENANT:
                raise serializers.ValidationError({
                    "agency": "L'agence principale est obligatoire."
                })
            if agency is not None and tenant and agency.tenant_id != tenant.id:
                raise serializers.ValidationError({
                    "agency": "L'agence doit appartenir à la filiale."
                })
            if agencies:
                for ag in agencies:
                    if tenant and ag.tenant_id != tenant.id:
                        raise serializers.ValidationError({
                            "agency_ids": "Toutes les agences doivent appartenir à la filiale."
                        })
        elif tenant is not None:
            raise serializers.ValidationError({
                "tenant": "Un utilisateur Groupe ne doit pas être rattaché à une filiale."
            })
        elif agency is not None or agencies:
            raise serializers.ValidationError({"agency": "Un utilisateur Groupe ne doit pas être rattaché à une agence."})
        # Un changement de filiale doit aussi revalider les rôles existants.
        groups = attrs.get("groups")
        if groups is None and self.instance is not None:
            groups = list(self.instance.groups.all())
        if tenant is not None and groups:
            try:
                validate_groups_for_tenant(tenant.pk, groups)
                validate_sod_role_assignment(groups)
            except ValueError as exc:
                raise serializers.ValidationError({"group_ids": str(exc)})
        return attrs

    def create(self, validated_data):
        agencies = validated_data.pop("agencies", None)
        user = super().create(validated_data)
        if agencies is not None:
            user.agencies.set(agencies)
        elif user.agency_id:
            user.agencies.add(user.agency)
        return user

    def update(self, instance, validated_data):
        agencies = validated_data.pop("agencies", None)
        user = super().update(instance, validated_data)
        if agencies is not None:
            user.agencies.set(agencies)
            if user.agency_id and not user.agencies.filter(pk=user.agency_id).exists():
                user.agencies.add(user.agency)
        return user


class UserCreateSerializer(serializers.ModelSerializer):
    group_ids = serializers.PrimaryKeyRelatedField(
        many=True, queryset=Group.objects.all(), source="groups",
        write_only=True, required=False,
    )
    agency_ids = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=Agency.objects.all(),
        source="agencies",
        write_only=True,
        required=False,
    )
    as_filiale_admin = serializers.BooleanField(
        write_only=True,
        required=False,
        default=False,
        help_text=(
            "Si vrai (admin Groupe uniquement) : crée un administrateur "
            "filiale (is_staff, data_scope TENANT, rôle Administrateur filiale "
            "= menus d'administration + fonctionnalités métier, "
            "exclusivement sur cette filiale)."
        ),
    )
    password_delivery = serializers.ChoiceField(
        choices=["email", "manual"],
        required=False,
        default="email",
        write_only=True,
        help_text="email = générer et envoyer ; manual = mot de passe saisi.",
    )
    password = serializers.CharField(
        write_only=True, required=False, allow_blank=True, min_length=10
    )
    password_confirm = serializers.CharField(
        write_only=True, required=False, allow_blank=True, min_length=10
    )
    email_sent = serializers.SerializerMethodField(read_only=True)
    password_delivery_mode = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = User
        fields = [
            "id", "username", "email", "first_name", "last_name",
            "tenant", "agency", "agency_ids", "data_scope",
            "is_group_level", "employee_id", "cbs_id", "phone",
            "is_active", "group_ids", "as_filiale_admin",
            "password_delivery", "password", "password_confirm",
            "email_sent", "password_delivery_mode",
        ]
        extra_kwargs = {
            "email": {"required": False, "allow_blank": True},
        }

    def get_email_sent(self, obj):
        return bool(getattr(obj, "_email_sent", False))

    def get_password_delivery_mode(self, obj):
        return getattr(obj, "_password_delivery", "email")

    def validate_cbs_id(self, value):
        from apps.catalog.cbs_validation import validate_manager_cbs_id
        from apps.common.tenancy import get_current_tenant_id

        tenant_id = self.initial_data.get("tenant") or get_current_tenant_id()
        return validate_manager_cbs_id(value, tenant_id=tenant_id)

    def validate(self, attrs):
        from .password_services import validate_password_delivery

        validate_account_administration(attrs, None, self.context)
        as_admin = attrs.pop("as_filiale_admin", False)
        request = self.context.get("request")
        actor = getattr(request, "user", None) if request else None

        attrs = validate_password_delivery(attrs, email_field="email")

        if as_admin:
            if not (
                actor
                and (
                    getattr(actor, "is_group_level", False)
                    or actor.is_superuser
                )
            ):
                raise serializers.ValidationError({
                    "as_filiale_admin": (
                        "Seul un administrateur Groupe peut provisionner "
                        "un admin filiale."
                    )
                })
            if attrs.get("is_group_level"):
                raise serializers.ValidationError({
                    "as_filiale_admin": (
                        "Un admin filiale ne peut pas être un utilisateur Groupe."
                    )
                })
            attrs["_as_filiale_admin"] = True

        is_group = attrs.get("is_group_level", False)
        tenant = attrs.get("tenant")
        tenant_id = get_current_tenant_id()

        if not is_group:
            if tenant is None:
                if tenant_id:
                    from apps.tenants.models import Tenant
                    attrs["tenant"] = Tenant.objects.get(pk=tenant_id)
                else:
                    raise serializers.ValidationError({
                        "tenant": "La filiale est obligatoire pour un utilisateur filiale."
                    })
            agency = attrs.get("agency")
            if as_admin:
                # Admin filiale = périmètre toute la filiale ; agence optionnelle.
                attrs["data_scope"] = DataScope.TENANT
                if agency is not None and agency.tenant_id != attrs["tenant"].id:
                    raise serializers.ValidationError({
                        "agency": "L'agence doit appartenir à la filiale."
                    })
                agencies = attrs.get("agencies", [])
                for ag in agencies:
                    if ag.tenant_id != attrs["tenant"].id:
                        raise serializers.ValidationError({
                            "agency_ids": "Toutes les agences doivent appartenir à la filiale."
                        })
                if not agencies and agency is not None:
                    attrs["agencies"] = [agency]
            else:
                if agency is None:
                    raise serializers.ValidationError({
                        "agency": "L'agence principale est obligatoire."
                    })
                if agency.tenant_id != attrs["tenant"].id:
                    raise serializers.ValidationError({
                        "agency": "L'agence doit appartenir à la filiale."
                    })
                agencies = attrs.get("agencies", [])
                if agencies:
                    for ag in agencies:
                        if ag.tenant_id != attrs["tenant"].id:
                            raise serializers.ValidationError({
                                "agency_ids": "Toutes les agences doivent appartenir à la filiale."
                            })
                else:
                    attrs["agencies"] = [agency]
            groups = attrs.get("groups", [])
            if groups:
                try:
                    validate_groups_for_tenant(attrs["tenant"].id, groups)
                    validate_sod_role_assignment(groups)
                except ValueError as exc:
                    raise serializers.ValidationError({"group_ids": str(exc)})
        elif tenant is not None:
            raise serializers.ValidationError({
                "tenant": "Un utilisateur Groupe ne doit pas être rattaché à une filiale."
            })
        else:
            if attrs.get("agency") is not None or attrs.get("agencies"):
                raise serializers.ValidationError({"agency": "Un utilisateur Groupe ne doit pas être rattaché à une agence."})
            attrs["data_scope"] = DataScope.TENANT
        return attrs

    def create(self, validated_data):
        from .password_services import (
            PASSWORD_DELIVERY_EMAIL,
            assign_password,
            issue_temporary_password,
        )

        as_admin = validated_data.pop("_as_filiale_admin", False)
        groups = validated_data.pop("groups", [])
        agencies = validated_data.pop("agencies", [])
        delivery = validated_data.pop("password_delivery", PASSWORD_DELIVERY_EMAIL)
        raw_password = validated_data.pop("password", None) or None
        validated_data.pop("password_confirm", None)

        if as_admin:
            from .services import provision_filiale_admin

            send_mail = delivery == PASSWORD_DELIVERY_EMAIL
            user, _ = provision_filiale_admin(
                tenant=validated_data["tenant"],
                agency=validated_data.get("agency"),
                username=validated_data["username"],
                password=None if send_mail else raw_password,
                email=validated_data.get("email", ""),
                first_name=validated_data.get("first_name", ""),
                last_name=validated_data.get("last_name", ""),
                phone=validated_data.get("phone", ""),
                employee_id=validated_data.get("employee_id", ""),
                cbs_id=validated_data.get("cbs_id", ""),
                agency_ids=agencies,
                send_credentials=send_mail,
                must_change_password=True,
            )
            if groups:
                try:
                    validate_groups_for_tenant(user.tenant_id, groups)
                    validate_sod_role_assignment(groups)
                except ValueError as exc:
                    raise serializers.ValidationError({"group_ids": str(exc)})
                user.groups.add(*groups)
            user._password_delivery = delivery  # noqa: SLF001
            return user

        validated_data["must_change_password"] = True
        user = User(**validated_data)
        user.set_unusable_password()
        user.full_clean()
        user.save()
        if agencies:
            user.agencies.set(agencies)
        elif user.agency_id:
            user.agencies.add(user.agency)
        if groups:
            user.groups.set(groups)

        if delivery == PASSWORD_DELIVERY_EMAIL:
            _, email_sent = issue_temporary_password(
                user, reason="created", send_email=True
            )
            user._email_sent = email_sent  # noqa: SLF001
        else:
            try:
                assign_password(user, raw_password, must_change_password=True)
            except Exception as exc:  # noqa: BLE001 — ValidationError Django
                user.delete()
                raise serializers.ValidationError({
                    "password": list(exc.messages)
                    if hasattr(exc, "messages")
                    else [str(exc)]
                }) from exc
            user._email_sent = False  # noqa: SLF001
        user._password_delivery = delivery  # noqa: SLF001
        return user


class ProvisionFilialeAdminSerializer(serializers.Serializer):
    """Payload dédié : création d'un admin filiale par l'admin Groupe."""

    username = serializers.CharField(max_length=150)
    email = serializers.EmailField(required=False, allow_blank=True)
    first_name = serializers.CharField(
        required=False, allow_blank=True, default="", max_length=150
    )
    last_name = serializers.CharField(
        required=False, allow_blank=True, default="", max_length=150
    )
    phone = serializers.CharField(
        required=False, allow_blank=True, default="", max_length=30
    )
    employee_id = serializers.CharField(
        required=False, allow_blank=True, default="", max_length=50
    )
    cbs_id = serializers.CharField(
        required=False, allow_blank=True, default="", max_length=64
    )
    tenant = serializers.UUIDField(required=False)
    agency = serializers.UUIDField(required=False, allow_null=True)
    agency_ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        default=list,
    )
    password_delivery = serializers.ChoiceField(
        choices=["email", "manual"],
        required=False,
        default="email",
    )
    password = serializers.CharField(
        write_only=True, required=False, allow_blank=True, min_length=10
    )
    password_confirm = serializers.CharField(
        write_only=True, required=False, allow_blank=True, min_length=10
    )

    def validate_cbs_id(self, value):
        from apps.catalog.cbs_validation import validate_manager_cbs_id
        from apps.common.tenancy import get_current_tenant_id

        tenant_id = self.initial_data.get("tenant") or get_current_tenant_id()
        return validate_manager_cbs_id(value, tenant_id=tenant_id)

    def validate(self, attrs):
        from apps.tenants.models import Agency, Tenant
        from .password_services import validate_password_delivery

        attrs = validate_password_delivery(attrs, email_field="email")

        tenant_id = attrs.get("tenant") or get_current_tenant_id()
        if not tenant_id:
            raise serializers.ValidationError({
                "tenant": (
                    "Indiquez la filiale (champ tenant ou en-tête X-Tenant-Id)."
                )
            })
        try:
            tenant = Tenant.objects.get(pk=tenant_id)
        except Tenant.DoesNotExist as exc:
            raise serializers.ValidationError({
                "tenant": "Filiale introuvable."
            }) from exc

        agency = None
        agency_id = attrs.get("agency")
        if agency_id:
            try:
                agency = Agency.objects.get(pk=agency_id)
            except Agency.DoesNotExist as exc:
                raise serializers.ValidationError({
                    "agency": "Agence introuvable."
                }) from exc
            if agency.tenant_id != tenant.id:
                raise serializers.ValidationError({
                    "agency": "L'agence doit appartenir à la filiale."
                })

        extra_ids = attrs.get("agency_ids") or []
        agencies = []
        for aid in extra_ids:
            try:
                ag = Agency.objects.get(pk=aid)
            except Agency.DoesNotExist as exc:
                raise serializers.ValidationError({
                    "agency_ids": f"Agence introuvable : {aid}."
                }) from exc
            if ag.tenant_id != tenant.id:
                raise serializers.ValidationError({
                    "agency_ids": "Toutes les agences doivent appartenir à la filiale."
                })
            agencies.append(ag)

        attrs["tenant_obj"] = tenant
        attrs["agency_obj"] = agency
        attrs["agency_objs"] = agencies
        return attrs

    def create(self, validated_data):
        from .password_services import PASSWORD_DELIVERY_EMAIL
        from .services import provision_filiale_admin

        delivery = validated_data.get("password_delivery", PASSWORD_DELIVERY_EMAIL)
        send_mail = delivery == PASSWORD_DELIVERY_EMAIL
        raw_password = validated_data.get("password") or None

        user, created = provision_filiale_admin(
            tenant=validated_data["tenant_obj"],
            agency=validated_data.get("agency_obj"),
            username=validated_data["username"],
            password=None if send_mail else raw_password,
            email=validated_data.get("email", ""),
            first_name=validated_data.get("first_name", ""),
            last_name=validated_data.get("last_name", ""),
            phone=validated_data.get("phone", ""),
            employee_id=validated_data.get("employee_id", ""),
            cbs_id=validated_data.get("cbs_id", ""),
            agency_ids=validated_data.get("agency_objs") or [],
            send_credentials=send_mail,
            must_change_password=True,
        )
        user._provision_created = created  # noqa: SLF001
        user._password_delivery = delivery  # noqa: SLF001
        return user


class AdminSetPasswordSerializer(serializers.Serializer):
    """Régénération de mot de passe par un administrateur."""

    password_delivery = serializers.ChoiceField(
        choices=["email", "manual"],
        required=False,
        default="email",
    )
    password = serializers.CharField(
        write_only=True, required=False, allow_blank=True, min_length=10
    )
    password_confirm = serializers.CharField(
        write_only=True, required=False, allow_blank=True, min_length=10
    )

    def validate(self, attrs):
        from .password_services import (
            PASSWORD_DELIVERY_EMAIL,
            PASSWORD_DELIVERY_MANUAL,
        )

        delivery = attrs.get("password_delivery") or PASSWORD_DELIVERY_EMAIL
        attrs["password_delivery"] = delivery
        if delivery == PASSWORD_DELIVERY_MANUAL:
            password = attrs.get("password") or ""
            confirm = attrs.get("password_confirm") or ""
            if not password:
                raise serializers.ValidationError({
                    "password": "Indiquez le mot de passe à attribuer."
                })
            if password != confirm:
                raise serializers.ValidationError({
                    "password_confirm": "Les mots de passe ne correspondent pas."
                })
        elif delivery != PASSWORD_DELIVERY_EMAIL:
            raise serializers.ValidationError({
                "password_delivery": "Choix invalide (email ou manual)."
            })
        return attrs


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, min_length=10)
    new_password_confirm = serializers.CharField(write_only=True, min_length=10)

    def validate(self, attrs):
        if attrs["new_password"] != attrs["new_password_confirm"]:
            raise serializers.ValidationError({
                "new_password_confirm": "Les mots de passe ne correspondent pas."
            })
        from django.contrib.auth.password_validation import validate_password

        user = self.context["request"].user
        try:
            validate_password(attrs["new_password"], user=user)
        except Exception as exc:  # noqa: BLE001 — ValidationError Django
            raise serializers.ValidationError({
                "new_password": list(exc.messages)
                if hasattr(exc, "messages")
                else [str(exc)]
            }) from exc
        return attrs


class MeSerializer(serializers.ModelSerializer):
    permissions = serializers.SerializerMethodField()
    roles = serializers.SerializerMethodField()
    tenant_branding = serializers.SerializerMethodField()
    features = serializers.SerializerMethodField()
    capabilities = serializers.SerializerMethodField()
    agencies_detail = AgencySummarySerializer(
        source="agencies", many=True, read_only=True
    )

    class Meta:
        model = User
        fields = [
            "id", "username", "email", "first_name", "last_name",
            "tenant", "agency", "agencies_detail", "data_scope",
            "is_group_level", "is_staff", "is_superuser", "mfa_enabled",
            "must_change_password", "roles", "permissions", "tenant_branding",
            "features", "capabilities",
        ]

    def get_permissions(self, obj):
        return sorted(obj.get_all_permissions())

    def get_capabilities(self, obj):
        from .capabilities import user_capabilities
        return sorted(user_capabilities(obj))

    def get_roles(self, obj):
        names = []
        for group in obj.groups.select_related("tenant_role").all():
            tr = getattr(group, "tenant_role", None)
            names.append(tr.name if tr else group.name)
        return names

    def get_features(self, obj):
        from django.conf import settings

        return {"sms": bool(getattr(settings, "FEATURE_SMS", False))}

    def get_tenant_branding(self, obj):
        from apps.common.storage_urls import tenant_logo_url

        tenant = obj.tenant
        if tenant is None:
            return None
        request = self.context.get("request")
        return {
            "id": str(tenant.id),
            "code": tenant.code,
            "name": tenant.name,
            "logo_url": tenant_logo_url(tenant, request),
            "brand_primary": tenant.brand_primary,
            "brand_secondary": tenant.brand_secondary,
            "brand_accent": tenant.brand_accent,
            "brand_sidebar": tenant.brand_sidebar,
            "brand_sidebar_text": tenant.brand_sidebar_text,
        }


class DelegationSerializer(serializers.ModelSerializer):
    is_currently_valid = serializers.BooleanField(read_only=True)
    delegator_display = serializers.SerializerMethodField()
    delegate_display = serializers.SerializerMethodField()

    class Meta:
        model = Delegation
        fields = [
            "id",
            "delegator",
            "delegator_display",
            "delegate",
            "delegate_display",
            "reason",
            "start_date",
            "end_date",
            "is_active",
            "is_currently_valid",
            "max_amount", "product", "agency", "step_kind", "approval_required", "approved_by", "approved_at",
            "created_at",
        ]
        read_only_fields = [
            "approval_required", "approved_by", "approved_at",
            "id",
            "created_at",
            "delegator_display",
            "delegate_display",
            "is_currently_valid",
        ]

    def get_delegator_display(self, obj):
        user = obj.delegator
        if user is None:
            return ""
        return user.get_full_name() or user.username

    def get_delegate_display(self, obj):
        user = obj.delegate
        if user is None:
            return ""
        return user.get_full_name() or user.username

    def validate(self, attrs):
        delegator = attrs.get("delegator")
        delegate = attrs.get("delegate")
        if self.instance is not None:
            if delegator is None:
                delegator = self.instance.delegator
            if delegate is None:
                delegate = self.instance.delegate
        if delegator and delegate and delegator.pk == delegate.pk:
            raise serializers.ValidationError(
                {"delegate": "Le délégataire doit être distinct du délégant."}
            )
        start = attrs.get("start_date")
        end = attrs.get("end_date")
        if self.instance is not None:
            if start is None:
                start = self.instance.start_date
            if end is None:
                end = self.instance.end_date
        if start and end and end < start:
            raise serializers.ValidationError(
                {"end_date": "La date de fin doit être postérieure ou égale au début."}
            )
        for field in ("product", "agency"):
            value = attrs.get(field, getattr(self.instance, field, None))
            if value and delegator and value.tenant_id != delegator.tenant_id:
                raise serializers.ValidationError({field: "Le périmètre doit appartenir à la filiale du délégant."})
        if delegate and delegator and delegate.tenant_id != delegator.tenant_id:
            raise serializers.ValidationError({"delegate": "La délégation doit rester dans la même filiale."})
        tenant_id = get_current_tenant_id()
        if tenant_id and delegator and str(delegator.tenant_id) != str(tenant_id):
            raise serializers.ValidationError({"delegator": "Le délégant doit appartenir à la filiale sélectionnée."})
        maximum = attrs.get("max_amount")
        if maximum is not None and maximum < 0:
            raise serializers.ValidationError({"max_amount": "Le plafond ne peut être négatif."})
        return attrs


class DelegationGiveSerializer(serializers.Serializer):
    """Création self-service : le délégant est l'utilisateur connecté."""

    delegate = serializers.UUIDField()
    reason = serializers.CharField(required=False, allow_blank=True, max_length=255)
    start_date = serializers.DateField()
    end_date = serializers.DateField()

    def validate(self, attrs):
        if attrs["end_date"] < attrs["start_date"]:
            raise serializers.ValidationError(
                {"end_date": "La date de fin doit être postérieure ou égale au début."}
            )
        return attrs
