#!/bin/sh
set -eu
cd /product/backend
uv run --no-sync alembic -c business-alembic.ini upgrade head
exec uv run --no-sync uvicorn delivery_entry:create_app --factory --host 0.0.0.0 --port 8000
