FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Dependencies are copied first so that editing application code does not
# invalidate the (slow) pip layer.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Static files are baked into the image; WhiteNoise serves them at runtime.
# The placeholder key is only needed to import settings during the build and
# never leaves this layer.
RUN DEBUG=True DJANGO_SECRET_KEY=build-time-placeholder \
    python manage.py collectstatic --noinput

# Run as an unprivileged user.
RUN useradd --create-home --uid 1000 appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python /app/healthcheck.py

ENTRYPOINT ["/app/entrypoint.sh"]
# Bind address and worker count come from gunicorn.conf.py, which reads $PORT.
CMD ["gunicorn", "HotelBookingAPI.wsgi:application", "-c", "gunicorn.conf.py"]
