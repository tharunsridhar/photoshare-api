#!/bin/sh
# Runs before the CMD on every container start. docker-compose's
# `depends_on: postgres: condition: service_healthy` guarantees Postgres is
# already accepting connections by the time this runs.
set -e

echo "Running database migrations..."
python manage.py migrate --noinput

echo "Collecting static files..."
python manage.py collectstatic --noinput

echo "Starting application..."
exec "$@"
