"""Authentification JWT + MFA TOTP."""
from __future__ import annotations

import pyotp
from django.contrib.auth import authenticate, get_user_model
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.tokens import RefreshToken

User = get_user_model()


class FinFlowTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Login JWT avec étape MFA optionnelle (champ ``otp``)."""

    otp = serializers.CharField(required=False, allow_blank=True, write_only=True)

    def validate(self, attrs):
        username_field = self.username_field
        authenticate_kwargs = {
            username_field: attrs[username_field],
            "password": attrs["password"],
        }
        request = self.context.get("request")
        if request:
            authenticate_kwargs["request"] = request

        self.user = authenticate(**authenticate_kwargs)
        if self.user is None or not self.user.is_active:
            raise AuthenticationFailed(
                detail="Identifiants invalides.",
                code="authorization",
            )

        if self.user.mfa_enabled:
            otp = (attrs.get("otp") or "").strip()
            if not otp:
                raise AuthenticationFailed(
                    detail={
                        "code": "mfa_required",
                        "detail": "Code MFA requis.",
                    },
                    code="mfa_required",
                )
            if not self.user.mfa_secret or not pyotp.TOTP(self.user.mfa_secret).verify(
                otp, valid_window=1
            ):
                raise AuthenticationFailed(
                    detail={
                        "code": "mfa_invalid",
                        "detail": "Code MFA invalide.",
                    },
                    code="mfa_invalid",
                )

        refresh = self.get_token(self.user)
        return {
            "refresh": str(refresh),
            "access": str(refresh.access_token),
            "must_change_password": bool(self.user.must_change_password),
        }


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField()

    def save(self, **kwargs):
        try:
            token = RefreshToken(self.validated_data["refresh"])
            token.blacklist()
        except Exception as exc:  # noqa: BLE001
            raise serializers.ValidationError(
                {"refresh": "Jeton de rafraîchissement invalide."}
            ) from exc


class MfaSetupSerializer(serializers.Serializer):
    """Réponse d'enrôlement MFA (secret + URI otpauth)."""

    secret = serializers.CharField(read_only=True)
    provisioning_uri = serializers.CharField(read_only=True)


class MfaConfirmSerializer(serializers.Serializer):
    otp = serializers.CharField(min_length=6, max_length=8)


class MfaDisableSerializer(serializers.Serializer):
    otp = serializers.CharField(min_length=6, max_length=8)
    password = serializers.CharField(write_only=True)
