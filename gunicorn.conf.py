"""Gunicorn configuration.

Kept as a file rather than command-line flags because the port has to be read
from the environment: Render (and most PaaS hosts) inject $PORT at runtime,
and an exec-form Docker CMD does no shell expansion.
"""

import os


def _env(name: str, default: str) -> str:
    """Read an env var, treating an empty value as absent.

    Compose and some PaaS hosts pass through variables that were never set as
    empty strings, which `os.getenv(name, default)` would hand back verbatim.
    """
    return os.getenv(name) or default


bind = f"0.0.0.0:{_env('PORT', '8000')}"
workers = int(_env("WEB_CONCURRENCY", "3"))
timeout = int(_env("WEB_TIMEOUT", "60"))

# Logs go to the container's stdout/stderr for the platform to collect.
accesslog = "-"
errorlog = "-"
access_log_format = '%(h)s "%(r)s" %(s)s %(b)s %(M)sms'
