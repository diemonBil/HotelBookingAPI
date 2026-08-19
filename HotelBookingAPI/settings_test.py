"""Settings used by the test suite.

Kept separate so that a developer's local ``.env`` can never change what the
tests run against, and so production hardening (HTTPS redirects, HSTS) does
not interfere with the test client.
"""

import os

import dj_database_url

from .settings import *  # noqa: F403

DEBUG = True

# Production hardening from the base module, switched off for the test client.
SECURE_SSL_REDIRECT = False
SECURE_HSTS_SECONDS = 0
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False

# SQLite by default, because it needs no service and keeps the suite fast.
# Set TEST_DATABASE_URL to run against PostgreSQL instead, which is the only
# way to exercise the SELECT ... FOR UPDATE path in the booking service.
_test_database_url = os.getenv("TEST_DATABASE_URL")
if _test_database_url:
    DATABASES = {"default": dj_database_url.parse(_test_database_url)}
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": ":memory:",
        }
    }

# No network calls from tests.
PAYMENT_PROVIDER = "fake"
PUBLIC_BASE_URL = "http://testserver"
MONOBANK_TOKEN = ""

# Hashing dominates the runtime of auth tests; correctness of the hashing
# itself is Django's concern, not this project's.
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# Nothing has been collected into STATIC_ROOT during a test run, and WhiteNoise
# warns about that on every single request.
MIDDLEWARE = [m for m in MIDDLEWARE if "whitenoise" not in m]  # noqa: F405

# A local-memory cache keeps throttle counters isolated per test process.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}
