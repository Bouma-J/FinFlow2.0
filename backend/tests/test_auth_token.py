import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User

pytestmark = pytest.mark.django_db


def test_token_unknown_user_returns_401_envelope():
    api = APIClient()
    res = api.post(
        "/api/v1/auth/token/",
        {"username": "inconnu", "password": "x"},
        format="json",
    )
    assert res.status_code == 401
    body = res.json()
    assert body["success"] is False
    assert body["errors"]["detail"] == "Identifiants invalides."


def test_token_valid_user_returns_jwt_pair():
    User.objects.create_user(
        username="login_ok",
        password="x",
        is_group_level=True,
        is_staff=True,
    )
    api = APIClient()
    res = api.post(
        "/api/v1/auth/token/",
        {"username": "login_ok", "password": "x"},
        format="json",
    )
    assert res.status_code == 200, res.content
    body = res.json()
    assert body["access"]
    assert body["refresh"]
    assert body["must_change_password"] is False
