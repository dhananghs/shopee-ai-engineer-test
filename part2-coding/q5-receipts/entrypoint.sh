#!/bin/sh
# Runs before the web server every time the container starts.
set -e

DB_HOST=${DB_HOST:-localhost}
DB_PORT=${DB_PORT:-5432}

# The database is question 4's container, which is a separate compose project,
# so "depends_on: service_healthy" cannot reach it. Without waiting here the
# first start races postgres and dies on "connection refused".
echo "waiting for postgres at $DB_HOST:$DB_PORT ..."
until python -c "import os, socket; socket.create_connection((os.environ['DB_HOST'], int(os.environ['DB_PORT'])), 2)" 2>/dev/null; do
    sleep 2
done
echo "postgres is up"

# migrate on every start, not just the first. it does nothing when there is
# nothing new to apply, and it means a fresh volume works without a manual step.
python manage.py migrate --noinput

exec "$@"
