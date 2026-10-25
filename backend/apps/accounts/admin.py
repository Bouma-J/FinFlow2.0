from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.admin import GroupAdmin as BaseGroupAdmin
from django.contrib.auth.forms import UserChangeForm, UserCreationForm
from django.contrib.auth.models import Group
from django import forms

from .models import Delegation, TenantRole, User
from .capabilities import CAPABILITIES, group_capabilities, validate_capability_combination
from .services import validate_groups_for_tenant, validate_sod_role_assignment


class UserRoleValidationMixin:
    def clean(self):
        data = super().clean()
        groups = data.get("groups", [])
        tenant = data.get("tenant", self.instance.tenant if self.instance else None)
        try:
            if tenant:
                validate_groups_for_tenant(tenant.pk, groups)
            elif groups and any(getattr(group, "tenant_role", None) for group in groups):
                raise ValueError("Un compte Groupe ne peut recevoir un rôle de filiale.")
            validate_sod_role_assignment(groups)
        except ValueError as exc:
            raise forms.ValidationError(str(exc)) from exc
        return data


class AccountChangeForm(UserRoleValidationMixin, UserChangeForm):
    class Meta(UserChangeForm.Meta):
        model = User


class AccountCreationForm(UserRoleValidationMixin, UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = User


class BusinessGroupForm(forms.ModelForm):
    class Meta:
        model = Group
        fields = "__all__"

    def clean_permissions(self):
        permissions = self.cleaned_data["permissions"]
        codes = {
            p.codename.removeprefix("business_") for p in permissions
            if p.content_type.app_label == "accounts" and p.content_type.model == "user" and p.codename.startswith("business_") and p.codename.removeprefix("business_") in CAPABILITIES
        }
        try:
            validate_capability_combination(codes)
            if self.instance.pk:
                for user in self.instance.user_set.all():
                    combined = set(codes)
                    for other in user.groups.exclude(pk=self.instance.pk):
                        combined.update(group_capabilities(other))
                    validate_capability_combination(combined)
        except ValueError as exc:
            raise forms.ValidationError(str(exc)) from exc
        return permissions


if admin.site.is_registered(Group):
    admin.site.unregister(Group)


@admin.register(Group)
class BusinessGroupAdmin(BaseGroupAdmin):
    form = BusinessGroupForm

    def get_readonly_fields(self, request, obj=None):
        # L'intitulé libre est TenantRole.name. Le nom du groupe technique
        # transverse est une identité d'amorçage, pas un libellé éditorial.
        if obj and obj.name == "__ff_group__credit_committee":
            return ["name"]
        return super().get_readonly_fields(request, obj)


@admin.register(TenantRole)
class TenantRoleAdmin(admin.ModelAdmin):
    list_display = ["name", "tenant", "group", "created_at"]
    list_filter = ["tenant"]
    readonly_fields = ["pack_code"]

    def has_add_permission(self, request):
        # Le service crée ensemble rôle et groupe, avec l'audit associé.
        return False

    def get_readonly_fields(self, request, obj=None):
        return ["pack_code", "tenant", "group"] if obj else ["pack_code"]


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    form = AccountChangeForm
    add_form = AccountCreationForm
    list_display = [
        "username", "email", "first_name", "last_name",
        "tenant", "is_group_level", "is_active",
    ]
    list_filter = ["is_group_level", "is_active", "tenant", "groups"]
    fieldsets = BaseUserAdmin.fieldsets + (
        ("FIN_FLOW", {
            "fields": (
                "tenant", "agency", "is_group_level",
                "employee_id", "cbs_id", "phone", "mfa_enabled",
            )
        }),
    )


@admin.register(Delegation)
class DelegationAdmin(admin.ModelAdmin):
    list_display = [
        "delegator", "delegate", "start_date", "end_date", "is_active",
    ]
    list_filter = ["is_active"]
