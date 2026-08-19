"""Container health probe, used by the Dockerfile's HEALTHCHECK.

A separate file rather than an inline `python -c`, so that it can read $PORT
without fighting the quoting rules of an exec-form CMD.
"""

import os
import sys
import urllib.request

url = f"http://127.0.0.1:{os.getenv('PORT', '8000')}/api/v1/health/"

try:
    with urllib.request.urlopen(url, timeout=4) as response:  # noqa: S310
        sys.exit(0 if response.status == 200 else 1)
except Exception as exc:  # noqa: BLE001 - any failure means "not healthy"
    print(f"health check failed: {exc}", file=sys.stderr)
    sys.exit(1)
