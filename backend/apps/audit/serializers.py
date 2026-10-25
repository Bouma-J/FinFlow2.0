from rest_framework import serializers

from .models import AuditLog


class AuditLogSerializer(serializers.ModelSerializer):
    user_display = serializers.SerializerMethodField()

    def get_user_display(self, obj):
        return str(obj.user) if obj.user_id else ""

    class Meta:
        model = AuditLog
        fields = [
            "id", "tenant", "user", "user_display", "action",
            "model_label", "object_id", "object_repr", "changes",
            "ip_address", "timestamp",
        ]
        read_only_fields = fields
