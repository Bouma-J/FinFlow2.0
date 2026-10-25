"""
Configuration de base commune à tous les environnements FIN_FLOW.

Les réglages spécifiques à un environnement sont surchargés dans
`dev.py`, `prod.py` et `test.py`.
"""
from datetime import timedelta
from pathlib import Path

import environ

# BASE_DIR = .../backend
BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env(
    DJANGO_DEBUG=(bool, False),
    DJANGO_ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1"]),
    DJANGO_CORS_ALLOWED_ORIGINS=(list, []),
    JWT_ACCESS_TOKEN_LIFETIME_MINUTES=(int, 30),
    JWT_REFRESH_TOKEN_LIFETIME_DAYS=(int, 1),
    STORAGE_BACKEND=(str, "local"),
    GROUP_CONSOLIDATION_CURRENCY=(str, "XOF"),
    DB_CONN_MAX_AGE=(int, 60),
    AUDIT_RETENTION_DAYS=(int, 365),
    GED_SOFT_DELETE_RETENTION_DAYS=(int, 90),
    DASHBOARD_CACHE_TTL=(int, 45),
    ME_CACHE_TTL=(int, 60),
    CATALOG_CACHE_TTL=(int, 120),
    REPORTING_SNAPSHOT_MAX_AGE_SECONDS=(int, 3600),
    TENANT_ISOLATION_MODE=(str, "shared"),
    FEATURE_SMS=(bool, False),
)

# Chargement du fichier .env s'il existe
env_file = BASE_DIR / ".env"
if env_file.exists():
    environ.Env.read_env(str(env_file))

SECRET_KEY = env("DJANGO_SECRET_KEY", default="insecure-dev-key-change-me")
DEBUG = env("DJANGO_DEBUG")
ALLOW_SIMULATED_CBS_SETUP = False

# OpenAPI / Swagger : on en DEBUG ; forcer via ENABLE_API_DOCS=1 en prod si besoin
ENABLE_API_DOCS = env.bool("ENABLE_API_DOCS", default=DEBUG)
ALLOWED_HOSTS = env("DJANGO_ALLOWED_HOSTS")
FEATURE_SMS = env.bool("FEATURE_SMS", default=False)
# Fernet url-safe key (32 bytes b64). Vide = dérivée de SECRET_KEY.
FIELD_ENCRYPTION_KEY = env("FIELD_ENCRYPTION_KEY", default="")

# ---------------------------------------------------------------------------
# Applications
# ---------------------------------------------------------------------------
DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "django_filters",
    "drf_spectacular",
]

# Apps métier FIN_FLOW (ordre = dépendances : common et tenants d'abord)
LOCAL_APPS = [
    "apps.common",
    "apps.tenants",
    "apps.accounts",
    "apps.catalog",
    "apps.clients",
    "apps.credits",
    "apps.workflow",
    "apps.documents",
    "apps.guarantees",
    "apps.sureties",
    "apps.contracts",
    "apps.corebanking",
    "apps.collections",
    "apps.audit",
    "apps.reporting",
    "apps.notifications",
    "apps.configuration",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------
MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # Résout et isole le tenant courant (multi-tenants)
    "apps.common.middleware.CurrentTenantMiddleware",
    # Latence HTTP (observabilité)
    "apps.common.middleware.RequestTimingMiddleware",
    # Renseigne l'utilisateur courant pour la piste d'audit
    "apps.audit.middleware.AuditContextMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# ---------------------------------------------------------------------------
# Base de données
# ---------------------------------------------------------------------------
# Repli SQLite en dev si DATABASE_URL est absent (démarrage immédiat).
# En production, DATABASE_URL DOIT pointer vers PostgreSQL.
_database_url = env("DATABASE_URL", default="")
if _database_url:
    DATABASES = {"default": env.db_url_config(_database_url)}
    # Réutilisation des connexions Postgres (Gunicorn multi-workers).
    # Avec PgBouncer en mode transaction, fixer DB_CONN_MAX_AGE=0.
    DATABASES["default"]["CONN_MAX_AGE"] = env("DB_CONN_MAX_AGE")
    DATABASES["default"]["CONN_HEALTH_CHECKS"] = True
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

# ---------------------------------------------------------------------------
# Authentification
# ---------------------------------------------------------------------------
AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
     "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ---------------------------------------------------------------------------
# Internationalisation
# ---------------------------------------------------------------------------
LANGUAGE_CODE = "fr-fr"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------------------
# Fichiers statiques et médias
# ---------------------------------------------------------------------------
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "media/"
MEDIA_ROOT = Path(env("MEDIA_ROOT", default=str(BASE_DIR / "media")))

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# Django REST Framework
# ---------------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
        "apps.common.permissions.MustChangePasswordGate",
    ),
    "DEFAULT_PAGINATION_CLASS": "apps.common.pagination.DefaultPagination",
    "PAGE_SIZE": 25,
    "DEFAULT_FILTER_BACKENDS": (
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ),
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "apps.common.exceptions.custom_exception_handler",
    "DEFAULT_THROTTLE_CLASSES": (
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
        "apps.common.throttling.BurstUserRateThrottle",
    ),
    "DEFAULT_THROTTLE_RATES": {
        "user": "5000/day",
        # Les écrans métier chargent plusieurs synthèses par dossier ; garder
        # une marge pour une navigation rapide sans supprimer l'anti-rafale.
        "user_burst": env("API_USER_BURST_RATE", default="300/min"),
        "anon": "200/hour",
        "login": "12/min",
    },
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(
        minutes=env("JWT_ACCESS_TOKEN_LIFETIME_MINUTES")
    ),
    "REFRESH_TOKEN_LIFETIME": timedelta(
        days=env("JWT_REFRESH_TOKEN_LIFETIME_DAYS")
    ),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
}

SPECTACULAR_SETTINGS = {
    "TITLE": "FIN_FLOW API",
    "DESCRIPTION": "Plateforme SaaS multi-tenants de gestion des dossiers de crédit.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
}

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------
CORS_ALLOWED_ORIGINS = env("DJANGO_CORS_ALLOWED_ORIGINS")

# ---------------------------------------------------------------------------
# Celery (traitements asynchrones)
# ---------------------------------------------------------------------------
CELERY_BROKER_URL = env("CELERY_BROKER_URL", default="redis://localhost:6379/0")
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", default="redis://localhost:6379/1")
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE
# Robustesse sous charge / crash worker
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TASK_SOFT_TIME_LIMIT = env.int("CELERY_TASK_SOFT_TIME_LIMIT", default=300)
CELERY_TASK_TIME_LIMIT = env.int("CELERY_TASK_TIME_LIMIT", default=360)

# Cache Redis (throttle multi-workers, lectures chaudes futures)
_redis_cache_url = env("REDIS_CACHE_URL", default="")
if not _redis_cache_url:
    _broker = env("CELERY_BROKER_URL", default="redis://localhost:6379/0")
    if _broker.endswith("/0"):
        _redis_cache_url = _broker[:-1] + "2"
    else:
        _redis_cache_url = "redis://localhost:6379/2"
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": _redis_cache_url,
        "KEY_PREFIX": "finflow",
    }
}

# ---------------------------------------------------------------------------
# E-mail (alertes workflow)
# ---------------------------------------------------------------------------
EMAIL_BACKEND = env(
    "EMAIL_BACKEND",
    default="django.core.mail.backends.console.EmailBackend",
)
EMAIL_HOST = env("EMAIL_HOST", default="localhost")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
# Mot de passe d'application Gmail : les espaces éventuels sont ignorés
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="").replace(" ", "")
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)
EMAIL_USE_SSL = env.bool("EMAIL_USE_SSL", default=False)
# Vérif. certificat TLS SMTP. Mettre False en local si un antivirus
# (Avast Mail Shield) injecte un certificat auto-signé dans la chaîne.
SMTP_SSL_VERIFY = env.bool("SMTP_SSL_VERIFY", default=True)
DEFAULT_FROM_EMAIL = env(
    "DEFAULT_FROM_EMAIL", default="FIN_FLOW <noreply@finflow.local>"
)
SERVER_EMAIL = DEFAULT_FROM_EMAIL
FRONTEND_BASE_URL = env("FRONTEND_BASE_URL", default="http://localhost")
# URL publique de l'API (callbacks CBS Perfect). Ex. https://api.filiale.example
PUBLIC_API_BASE_URL = env("PUBLIC_API_BASE_URL", default="")

# ---------------------------------------------------------------------------
# Réglages métier FIN_FLOW
# ---------------------------------------------------------------------------
STORAGE_BACKEND = env("STORAGE_BACKEND")
GROUP_CONSOLIDATION_CURRENCY = env("GROUP_CONSOLIDATION_CURRENCY")
AUDIT_RETENTION_DAYS = env("AUDIT_RETENTION_DAYS")
GED_SOFT_DELETE_RETENTION_DAYS = env("GED_SOFT_DELETE_RETENTION_DAYS")
DASHBOARD_CACHE_TTL = env("DASHBOARD_CACHE_TTL")
ME_CACHE_TTL = env("ME_CACHE_TTL")
CATALOG_CACHE_TTL = env("CATALOG_CACHE_TTL")
REPORTING_SNAPSHOT_MAX_AGE_SECONDS = env("REPORTING_SNAPSHOT_MAX_AGE_SECONDS")
# shared = DB unique + tenant_id (défaut) | schema = préparation multi-schéma
TENANT_ISOLATION_MODE = env("TENANT_ISOLATION_MODE")

# Stockage documentaire compatible S3 (MinIO ou équivalent)
if STORAGE_BACKEND == "s3":
    STORAGES = {
        "default": {"BACKEND": "storages.backends.s3.S3Storage"},
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        },
    }
    AWS_ACCESS_KEY_ID = env("AWS_ACCESS_KEY_ID", default="")
    AWS_SECRET_ACCESS_KEY = env("AWS_SECRET_ACCESS_KEY", default="")
    AWS_STORAGE_BUCKET_NAME = env("AWS_STORAGE_BUCKET_NAME", default="finflow-documents")
    AWS_S3_ENDPOINT_URL = env("AWS_S3_ENDPOINT_URL", default=None)
    AWS_S3_REGION_NAME = env("AWS_S3_REGION_NAME", default="us-east-1")
    AWS_S3_SIGNATURE_VERSION = "s3v4"
    AWS_S3_ADDRESSING_STYLE = env("AWS_S3_ADDRESSING_STYLE", default="path")
    AWS_S3_FILE_OVERWRITE = False
    AWS_DEFAULT_ACL = None
    AWS_QUERYSTRING_AUTH = env.bool("AWS_QUERYSTRING_AUTH", default=True)
    # Domaine vu par le navigateur (ex. localhost:9000) — distinct de
    # AWS_S3_ENDPOINT_URL utilisé par le backend pour parler à MinIO.
    _s3_public = env("AWS_S3_CUSTOM_DOMAIN", default="")
    if _s3_public:
        AWS_S3_CUSTOM_DOMAIN = _s3_public
    AWS_S3_URL_PROTOCOL = env("AWS_S3_URL_PROTOCOL", default="http:")

# Formats et taille autorisés pour la GED (paramétrable)
GED_MAX_UPLOAD_SIZE_MB = env.int("GED_MAX_UPLOAD_SIZE_MB", default=25)
GED_ALLOWED_EXTENSIONS = [
    "pdf", "jpg", "jpeg", "png", "tiff", "docx", "xlsx",
]

# Aligné sur la GED : rejette tôt les corps trop gros (complément nginx 25m)
DATA_UPLOAD_MAX_MEMORY_SIZE = GED_MAX_UPLOAD_SIZE_MB * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024  # au-delà → fichier temporaire

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{asctime} [{levelname}] {name}: {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "verbose"},
    },
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        "finflow": {"handlers": ["console"], "level": "INFO", "propagate": False},
    },
}
