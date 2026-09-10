#!/bin/sh
set -eu
cd "$(dirname "$0")/.."

fresh=0
new_env=0
for arg in "$@"; do
  case "$arg" in
    --fresh) fresh=1 ;;
    --new-env) new_env=1 ;;
    -h|--help)
      cat <<'EOF'
Usage: ./scripts/start.sh [--fresh [--new-env]]

Default:
  Preserve .env, host data/, PostgreSQL, Redis and Temporal volumes.

--fresh:
  Explicitly reset this Compose project's named volumes and start with a fresh
  active data/ directory. Previous host data is moved to runtime/reset-backups/.
  Existing .env credentials are preserved.

--fresh --new-env:
  Also rotate .env into runtime/reset-backups/ and generate new credentials.
EOF
      exit 0
      ;;
    *)
      echo "Unknown argument: $arg" >&2
      exit 2
      ;;
  esac
done

if [ "$new_env" -eq 1 ] && [ "$fresh" -ne 1 ]; then
  echo "--new-env is only valid together with --fresh" >&2
  exit 2
fi

if [ "$fresh" -eq 1 ]; then
  if [ "$new_env" -eq 1 ]; then
    python3 scripts/reset_local.py --new-env
  else
    python3 scripts/reset_local.py
  fi
fi

python3 scripts/init_env.py --repair-data
python3 scripts/setup_toolchain.py
docker compose version
docker compose config --quiet
docker compose up --build -d
printf '\nOpen http://localhost:8000/api/v1/web/ and log in, then /api/v1/web/#/factory\n'
printf 'See docs/START_HERE.md for first-login and diagnosis instructions.\n'
