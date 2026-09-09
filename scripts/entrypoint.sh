#!/bin/sh
set -eu
cd /app
case "${1:-api}" in
  migrate) exec python -m alembic -c /app/alembic.ini upgrade head ;;
  worker) exec python -m factory.worker ;;
  api)
    cd /app/runtime/FastapiAdmin/backend
    exec python -m uvicorn factory.host:create_app --factory --host 0.0.0.0 --port 8000
    ;;
  *) exec "$@" ;;
esac
