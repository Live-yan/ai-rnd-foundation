#!/bin/sh
set -eu
mkdir -p locks
# Never redirect docker compose config to a shared file: it contains resolved secrets.
docker compose exec -T api cat /app/runtime/combined/uv.lock > locks/host.uv.lock
docker compose exec -T api cat /app/runtime/combined/pyproject.toml > locks/host.pyproject.toml
docker compose exec -T api python -c 'import importlib.metadata as m,json; print(json.dumps({d.metadata["Name"]:d.version for d in m.distributions()},indent=2))' > locks/host-packages.json
docker compose images --format json > locks/images.json
echo 'Saved real runtime lock evidence to locks/.'
