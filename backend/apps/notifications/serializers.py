from rest_framework import serializers

from .mail import normalize_smtp_host, normalize_smtp_security, resolve_from_email, tenant_has_smtp
from .models import NotificationLog, TenantNotificationSettings


def _looks_like_from_header(value: str) -> bool:
    """Accepte une adresse simple ou « Nom <email@domaine> »."""
    import re

    value = (value or "").strip()
    if not value:
        return True
    if re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
        return True
    return bool(
        re.fullmatch(
            r".+<\s*[^@\s]+@[^@\s]+\.[^@\s]+\s*>",
            value,
        )
    )


class TenantNotificationSettingsSerializer(serializers.ModelSerializer):
    smtp_password = serializers.CharField(
        write_only=True, required=False, allow_blank=True
    )
    smtp_password_configured = serializers.SerializerMethodField()
    smtp_configured = serializers.SerializerMethodField()
    effective_from_email = serializers.SerializerMethodField()

    class Meta:
        model = TenantNotificationSettings
        fields = [
            "id",
            "enabled",
            "notify_on_step",
            "notify_on_completion",
            "notify_on_rejection",
            "notify_on_return",
            "notify_collection_email",
            "notify_collection_sms",
            "notify_collection_transfer",
            "notify_collection_dialogue",
            "from_email",
            "reply_to",
            "cc_tenant_email",
            "smtp_host",
            "smtp_port",
            "smtp_use_tls",
            "smtp_use_ssl",
            "smtp_username",
            "smtp_password",
            "smtp_password_configured",
            "smtp_configured",
            "effective_from_email",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "updated_at",
            "smtp_password_configured",
            "smtp_configured",
            "effective_from_email",
        ]
        extra_kwargs = {
            "reply_to": {"required": False, "allow_blank": True},
            "from_email": {"required": False, "allow_blank": True},
            "smtp_host": {"required": False, "allow_blank": True},
            "smtp_username": {"required": False, "allow_blank": True},
        }

    def validate_from_email(self, value):
        value = (value or "").strip()
        if value and not _looks_like_from_header(value):
            raise serializers.ValidationError(
                "Indiquez une adresse e-mail valide, éventuellement "
                "sous la forme « Nom <adresse@domaine.com> »."
            )
        return value

    def validate_reply_to(self, value):
        return (value or "").strip()

    def validate(self, attrs):
        port = attrs.get(
            "smtp_port",
            getattr(self.instance, "smtp_port", 587),
        )
        use_tls = attrs.get(
            "smtp_use_tls",
            getattr(self.instance, "smtp_use_tls", True),
        )
        use_ssl = attrs.get(
            "smtp_use_ssl",
            getattr(self.instance, "smtp_use_ssl", False),
        )
        host = attrs.get(
            "smtp_host",
            getattr(self.instance, "smtp_host", ""),
        )
        host = normalize_smtp_host(host)
        port, use_tls, use_ssl = normalize_smtp_security(
            port, use_tls, use_ssl, host=host
        )
        if "smtp_host" in attrs or host:
            attrs["smtp_host"] = host
        attrs["smtp_port"] = port
        attrs["smtp_use_tls"] = use_tls
        attrs["smtp_use_ssl"] = use_ssl
        return attrs

    def get_smtp_password_configured(self, obj) -> bool:
        return bool(obj.smtp_password)

    def get_smtp_configured(self, obj) -> bool:
        return tenant_has_smtp(obj)

    def get_effective_from_email(self, obj) -> str:
        return resolve_from_email(obj, tenant=getattr(obj, "tenant", None))

    def update(self, instance, validated_data):
        from apps.common.secret_crypto import encrypt_str

        password = validated_data.pop("smtp_password", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if password is not None and str(password).strip():
            # App Passwords Gmail : espaces ignorés, puis chiffrement au repos
            instance.smtp_password = encrypt_str(str(password).replace(" ", ""))
        instance.save()
        return instance


class NotificationLogSerializer(serializers.ModelSerializer):
    kind_display = serializers.CharField(source="get_kind_display", read_only=True)
    status_display = serializers.CharField(
        source="get_status_display", read_only=True
    )

    class Meta:
        model = NotificationLog
        fields = [
            "id",
            "kind",
            "kind_display",
            "status",
            "status_display",
            "subject",
            "recipients",
            "body_preview",
            "error_message",
            "workflow_instance_id",
            "approval_task_id",
            "created_at",
        ]
        read_only_fields = fields
