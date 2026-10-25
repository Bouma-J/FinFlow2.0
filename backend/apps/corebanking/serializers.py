import copy

from rest_framework import serializers

from apps.common.secret_crypto import encrypt_auth_config

from .models import CoreBankingConnector, IntegrationLog
from .perfect_defaults import perfect_auth_config, perfect_mapping_rules


def _redact_mapping_rules_for_api(rules: dict | None) -> dict:
    """Masque callback_secret à la lecture API (flag configuré seulement)."""
    out = copy.deepcopy(rules or {})
    disbursement = out.get("disbursement")
    if isinstance(disbursement, dict):
        secret = (disbursement.get("callback_secret") or "").strip()
        disbursement["callback_secret_configured"] = bool(secret)
        disbursement["callback_secret"] = ""
        out["disbursement"] = disbursement
    return out


def _merge_mapping_rules(existing: dict | None, incoming: dict | None) -> dict:
    """
    Fusionne mapping_rules ; un callback_secret vide conserve l'existant
    (même logique que auth_config password).
    """
    merged = copy.deepcopy(existing or {})
    incoming = copy.deepcopy(incoming or {})
    for key, value in incoming.items():
        if key == "disbursement" and isinstance(value, dict):
            prev = dict(merged.get("disbursement") or {})
            new_secret = value.get("callback_secret", None)
            for dk, dv in value.items():
                if dk == "callback_secret":
                    continue
                prev[dk] = dv
            if new_secret not in (None, ""):
                prev["callback_secret"] = new_secret
            # Si clé absente du payload, ne pas toucher au secret existant.
            merged["disbursement"] = prev
        else:
            merged[key] = value
    return merged


class CoreBankingConnectorSerializer(serializers.ModelSerializer):
    class Meta:
        model = CoreBankingConnector
        fields = [
            "id", "name", "protocol", "base_url", "auth_config",
            "mapping_rules", "certificate_reference", "is_active",
            "timeout_seconds", "max_retries", "created_at",
        ]
        read_only_fields = ["id", "created_at"]
        extra_kwargs = {
            "auth_config": {"write_only": True, "required": False},
            "mapping_rules": {"required": False},
        }

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["mapping_rules"] = _redact_mapping_rules_for_api(
            data.get("mapping_rules")
        )
        return data

    def create(self, validated_data):
        """Applique les défauts Perfect si auth / mapping absents."""
        protocol = validated_data.get("protocol") or CoreBankingConnector.Protocol.REST
        if protocol == CoreBankingConnector.Protocol.REST:
            rules = validated_data.get("mapping_rules") or {}
            if not rules:
                validated_data["mapping_rules"] = perfect_mapping_rules(demo=False)
            auth = validated_data.get("auth_config") or {}
            if not auth:
                validated_data["auth_config"] = perfect_auth_config()
            elif "scope" not in auth:
                auth = {**perfect_auth_config(), **auth}
                validated_data["auth_config"] = auth
        if "auth_config" in validated_data:
            validated_data["auth_config"] = encrypt_auth_config(
                validated_data["auth_config"]
            )
        return super().create(validated_data)

    def update(self, instance, validated_data):
        """Fusionne auth_config (ne pas écraser password si omis)."""
        if "auth_config" in validated_data:
            incoming = validated_data.pop("auth_config") or {}
            merged = dict(instance.auth_config or {})
            for key, value in incoming.items():
                if value in (None, ""):
                    continue
                merged[key] = value
            if "scope" not in merged:
                merged["scope"] = perfect_auth_config()["scope"]
            validated_data["auth_config"] = encrypt_auth_config(merged)
        if "mapping_rules" in validated_data:
            validated_data["mapping_rules"] = _merge_mapping_rules(
                instance.mapping_rules,
                validated_data.get("mapping_rules"),
            )
        return super().update(instance, validated_data)


class IntegrationLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = IntegrationLog
        fields = [
            "id", "connector", "operation", "direction", "idempotency_key",
            "request_payload", "response_payload", "status", "attempts",
            "external_reference", "error_message", "created_at",
        ]
        read_only_fields = fields
