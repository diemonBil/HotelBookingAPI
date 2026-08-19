"""Django settings for the HotelBookingAPI project.

Every environment-specific value is read from environment variables so that the
same image can run locally, in CI and in production. See ``.env.example`` for
the full list of supported variables.
"""

import os
from datetime import timedelta
from pathlib import Path

import dj_database_url
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")


def env_bool(name: str, default: bool = False) -> bool:
    """Read a boolean env var, accepting the usual truthy spellings."""
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: str = "") -> list[str]:
    """Read a comma-separated env var into a list, dropping empty entries."""
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]


DEBUG = env_bool("DEBUG", False)

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "")
if not SECRET_KEY:
    if not DEBUG:
        raise RuntimeError(
            "DJANGO_SECRET_KEY must be set when DEBUG is off. "
            'Generate one with: python -c "import secrets; print(secrets.token_urlsafe(50))"'
        )
    # Predictable throwaway key so a fresh clone runs without any setup.
    SECRET_KEY = "django-insecure-local-development-key-do-not-use-in-production"

ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", "127.0.0.1,localhost")
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS")

# Render assigns the public hostname at deploy time, so it cannot be baked into
# ALLOWED_HOSTS by hand. Picking it up here keeps the blueprint config-free.
RENDER_HOSTNAME = os.getenv("RENDER_EXTERNAL_HOSTNAME")
if RENDER_HOSTNAME:
    ALLOWED_HOSTS.append(RENDER_HOSTNAME)
    CSRF_TRUSTED_ORIGINS.append(f"https://{RENDER_HOSTNAME}")


# Application definition

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "django_filters",
    "drf_spectacular",
    "hotel",
    "user",
]

AUTH_USER_MODEL = "user.User"

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "HotelBookingAPI.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "HotelBookingAPI.wsgi.application"


# Database
# A single DATABASE_URL keeps Postgres (compose/production) and SQLite
# (throwaway local runs) interchangeable without touching this file.

DATABASES = {
    "default": dj_database_url.parse(
        os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'db.sqlite3'}"),
        conn_max_age=int(os.getenv("DB_CONN_MAX_AGE", "60")),
        conn_health_checks=True,
    )
}


# REST framework

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_FILTER_BACKENDS": (
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ),
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_THROTTLE_CLASSES": (
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ),
    "DEFAULT_THROTTLE_RATES": {
        "anon": os.getenv("THROTTLE_ANON", "60/min"),
        "user": os.getenv("THROTTLE_USER", "300/min"),
        # Applied to registration and token endpoints to slow down credential stuffing.
        "auth": os.getenv("THROTTLE_AUTH", "10/min"),
    },
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=int(os.getenv("JWT_ACCESS_MINUTES", "60"))),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=int(os.getenv("JWT_REFRESH_DAYS", "7"))),
    "ROTATE_REFRESH_TOKENS": True,
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Hotel Booking API",
    "DESCRIPTION": (
        "REST API for browsing hotels, checking room availability, creating "
        "bookings and paying for them through a pluggable payment provider."
    ),
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    "SCHEMA_PATH_PREFIX": "/api/v1",
    # Booking and Payment both expose a "status" field; name their enums
    # explicitly instead of letting the generator invent a suffix.
    "ENUM_NAME_OVERRIDES": {
        "BookingStatusEnum": "hotel.models.BOOKING_STATUS_CHOICES",
        "PaymentStatusEnum": "hotel.models.PAYMENT_STATUS_CHOICES",
    },
}


# Password validation

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


# Internationalization

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True


# Static files

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
# The demo client is plain CSS and JavaScript with no build step, so its assets
# are collected straight from the source tree.
STATICFILES_DIRS = [BASE_DIR / "frontend"]

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        # The manifest backend rewrites asset URLs to hashed filenames, but it
        # can only resolve names that collectstatic has already written. During
        # development nothing has been collected, so {% static %} would raise.
        "BACKEND": (
            "django.contrib.staticfiles.storage.StaticFilesStorage"
            if DEBUG
            else "whitenoise.storage.CompressedManifestStaticFilesStorage"
        ),
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# Payments
# PAYMENT_PROVIDER selects the implementation in hotel/payments/. "fake" keeps
# the whole booking flow working locally and in tests without network access.

PAYMENT_PROVIDER = os.getenv("PAYMENT_PROVIDER", "fake")
PAYMENT_CURRENCY_CODE = int(os.getenv("PAYMENT_CURRENCY_CODE", "980"))  # ISO 4217: UAH
_default_base_url = f"https://{RENDER_HOSTNAME}" if RENDER_HOSTNAME else "http://localhost:8000"
PUBLIC_BASE_URL = (os.getenv("PUBLIC_BASE_URL") or _default_base_url).rstrip("/")

MONOBANK_TOKEN = os.getenv("MONOBANK_TOKEN", "")
MONOBANK_API_URL = os.getenv("MONOBANK_API_URL", "https://api.monobank.ua")
# Signature checking can only be disabled explicitly, and never outside DEBUG.
MONOBANK_VERIFY_WEBHOOK = env_bool("MONOBANK_VERIFY_WEBHOOK", True)


# Security hardening. Only meaningful once DEBUG is off, so they are grouped
# here instead of being sprinkled through the file.

if not DEBUG:
    SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", True)
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    # Platform health probes reach the container over plain HTTP; a 301 to
    # HTTPS would read as a failed check and the deploy would never go live.
    SECURE_REDIRECT_EXEMPT = [r"^api/v1/health/$"]
    SECURE_HSTS_SECONDS = int(os.getenv("SECURE_HSTS_SECONDS", "31536000"))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = "DENY"


LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{asctime} {levelname} {name} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "verbose"},
    },
    "root": {"handlers": ["console"], "level": os.getenv("LOG_LEVEL", "INFO")},
    "loggers": {
        "django.db.backends": {"level": "WARNING", "propagate": True},
    },
}
