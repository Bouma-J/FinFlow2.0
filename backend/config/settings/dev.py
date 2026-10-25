"""Configuration de développement."""
from .base import *  # noqa: F401,F403
from .base import INSTALLED_APPS, MIDDLEWARE

DEBUG = True
ALLOW_SIMULATED_CBS_SETUP = True

INSTALLED_APPS += ["debug_toolbar"]
MIDDLEWARE = ["debug_toolbar.middleware.DebugToolbarMiddleware"] + MIDDLEWARE

INTERNAL_IPS = ["127.0.0.1"]

# Envoi des emails : console par défaut ; surchargeable via EMAIL_BACKEND
# (ex. SMTP Gmail dans le fichier .env)
EMAIL_BACKEND = env(
    "EMAIL_BACKEND",
    default="django.core.mail.backends.console.EmailBackend",
)

# Exécution synchrone des tâches Celery en dev (pas besoin de broker)
CELERY_TASK_ALWAYS_EAGER = True
# Le suivi des tâches exécutées localement doit aussi retrouver leur résultat.
CELERY_TASK_STORE_EAGER_RESULT = True
CELERY_BROKER_URL = env("CELERY_BROKER_URL", default="memory://")
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", default="cache+memory://")

# Cache mémoire locale : login / throttle sans Redis obligatoire
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "finflow-dev",
    }
}
