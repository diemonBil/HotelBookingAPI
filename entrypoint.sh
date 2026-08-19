#!/bin/sh
# Applies pending migrations, then hands control to the container command.
set -e

echo "Applying database migrations..."
python manage.py migrate --noinput

if [ "${SEED_DEMO_DATA}" = "true" ]; then
    echo "Seeding demo data..."
    python manage.py seed_demo_data
fi

exec "$@"
