"""Configuration pour l'exécution des tests."""
from .base import *  # noqa: F401,F403

# Base de données en mémoire pour des tests rapides
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
CELERY_TASK_ALWAYS_EAGER = True
ALLOW_SIMULATED_CBS_SETUP = True
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
# Tests : docs montées pour les tests qui en ont besoin ; le test P3 vérifie le gate
ENABLE_API_DOCS = False
# Clé Fernet stable pour les tests (évite la dérivation SECRET_KEY)
FIELD_ENCRYPTION_KEY = "jyYZdpd3kTY2RiW3UUFhbGMQuJCrQIFjO1ed6zowfqk="
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}
