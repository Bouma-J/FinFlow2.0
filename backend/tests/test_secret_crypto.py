"""Tests chiffrement secrets au repos (SMTP / auth CBS)."""
import pytest
from django.test import override_settings

from apps.common.secret_crypto import (
    PREFIX,
    decrypt_auth_config,
    decrypt_str,
    encrypt_auth_config,
    encrypt_str,
)

pytestmark = pytest.mark.django_db


@override_settings(SECRET_KEY="unit-test-secret-key-for-fernet-derivation")
def test_encrypt_decrypt_roundtrip():
    cipher = encrypt_str("mon-mdp-smtp")
    assert cipher.startswith(PREFIX)
    assert cipher != "mon-mdp-smtp"
    assert decrypt_str(cipher) == "mon-mdp-smtp"


@override_settings(SECRET_KEY="unit-test-secret-key-for-fernet-derivation")
def test_plaintext_legacy_passthrough():
    assert decrypt_str("already-plain") == "already-plain"
    assert encrypt_str(encrypt_str("x")).startswith(PREFIX)


@override_settings(SECRET_KEY="unit-test-secret-key-for-fernet-derivation")
def test_auth_config_encrypts_sensitive_keys_only():
    cfg = encrypt_auth_config(
        {
            "username": "apiuser",
            "password": "secret",
            "scope": "perfect",
            "access_token": "tok123",
        }
    )
    assert cfg["username"] == "apiuser"
    assert cfg["scope"] == "perfect"
    assert cfg["password"].startswith(PREFIX)
    assert cfg["access_token"].startswith(PREFIX)
    plain = decrypt_auth_config(cfg)
    assert plain["password"] == "secret"
    assert plain["access_token"] == "tok123"
