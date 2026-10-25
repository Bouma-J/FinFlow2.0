"""Vues d'authentification JWT, logout blacklist et MFA."""

from django.contrib.auth import get_user_model
import pyotp
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from apps.common.cache_utils import invalidate_prefix
from apps.common.permissions import MustChangePasswordGate
from apps.common.throttling import LoginRateThrottle

from .auth_serializers import (
    FinFlowTokenObtainPairSerializer,
    LogoutSerializer,
    MfaConfirmSerializer,
    MfaDisableSerializer,
)

User = get_user_model()


class ThrottledTokenObtainPairView(TokenObtainPairView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [LoginRateThrottle]
    serializer_class = FinFlowTokenObtainPairSerializer


class ThrottledTokenRefreshView(TokenRefreshView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [LoginRateThrottle]


class LogoutView(APIView):
    """Invalide le refresh token (blacklist)."""

    permission_classes = [IsAuthenticated, MustChangePasswordGate]

    def post(self, request):
        serializer = LogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        invalidate_prefix("me", request.user.id)
        return Response({"detail": "Déconnexion effectuée."})


class MfaSetupView(APIView):
    """Génère un secret TOTP (pas encore activé tant que non confirmé)."""

    permission_classes = [IsAuthenticated, MustChangePasswordGate]

    def post(self, request):
        user = request.user
        secret = pyotp.random_base32()
        user.mfa_secret = secret
        # Ne pas activer tant que la confirmation OTP n'est pas passée.
        user.mfa_enabled = False
        user.save(update_fields=["mfa_secret", "mfa_enabled"])
        uri = pyotp.TOTP(secret).provisioning_uri(
            name=user.email or user.username,
            issuer_name="FIN_FLOW",
        )
        invalidate_prefix("me", user.id)
        return Response({"secret": secret, "provisioning_uri": uri})


class MfaConfirmView(APIView):
    """Confirme l'OTP et active le MFA."""

    permission_classes = [IsAuthenticated, MustChangePasswordGate]

    def post(self, request):
        serializer = MfaConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = request.user
        if not user.mfa_secret:
            return Response(
                {"detail": "Lancez d'abord l'enrôlement MFA."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        otp = serializer.validated_data["otp"]
        if not pyotp.TOTP(user.mfa_secret).verify(otp, valid_window=1):
            return Response(
                {"detail": "Code MFA invalide."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        user.mfa_enabled = True
        user.save(update_fields=["mfa_enabled"])
        invalidate_prefix("me", user.id)
        return Response({"mfa_enabled": True})


class MfaDisableView(APIView):
    """Désactive le MFA après vérification mot de passe + OTP."""

    permission_classes = [IsAuthenticated, MustChangePasswordGate]

    def post(self, request):
        serializer = MfaDisableSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = request.user
        if not user.check_password(serializer.validated_data["password"]):
            return Response(
                {"detail": "Mot de passe incorrect."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if user.mfa_enabled:
            otp = serializer.validated_data["otp"]
            if not user.mfa_secret or not pyotp.TOTP(user.mfa_secret).verify(
                otp, valid_window=1
            ):
                return Response(
                    {"detail": "Code MFA invalide."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        user.mfa_enabled = False
        user.mfa_secret = ""
        user.save(update_fields=["mfa_enabled", "mfa_secret"])
        invalidate_prefix("me", user.id)
        return Response({"mfa_enabled": False})
